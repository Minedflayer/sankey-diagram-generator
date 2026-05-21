# utils.py
import json
import re
import PyPDF2
from groq import Groq
import streamlit as st
from collections import defaultdict

# utils.py (Append to the bottom)
import plotly.graph_objects as go

def get_groq_client():
    """ Initializes Groq client using streamlit native secrets. """
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

def extract_data(text: str, model_name: str, temperature: float) -> dict:
    """
    Instructs the LLM to extract financial data strictly from the Income Statement / 
    Statement of Operations, ignoring balance sheets and cash flows.
    """
    client = get_groq_client()

    system_prompt = """
    You are an expert forensic financial analyst. Your job is to extract hierarchical financial flow data ONLY from the INCOME STATEMENT (Statement of Operations) to build a Center-Origin Sankey diagram.
    
    CRITICAL BOUNDARY RULES (WHAT TO IGNORE):
    1. ONLY extract revenues, costs of revenue, gross profit, operating expenses, and net income.
    2. STRICTLY IGNORE Balance Sheet items (e.g., Total Assets, Liabilities, Equity, Inventory, Accounts Receivable/Payable, Retained Earnings).
    3. STRICTLY IGNORE Cash Flow statement items (e.g., Operating Cash Flow, Free Cash Flow, Investing activities, Financing activities).
    4. Do not include any of the ignored items in your output.
    
    CRITICAL TIER RULES:
    The central node representing the total incoming money (e.g., "Total Revenue", "Total Net Sales", "Total Revenues") is ALWAYS Tier 0.
    
    LEFT SIDE (INCOMING REVENUES - Negative Tiers):
    - Lowest-level sub-categories -> Tier -2 or -3.
    - Mid-level aggregators -> Tier -1.
    - If a revenue stream has no sub-categories, it goes straight to Tier -1.
    - JSON Direction MUST be: [Source: Sub-category -> Target: Aggregator or Tier 0].
    
    RIGHT SIDE (OUTGOING COSTS/PROFITS - Positive Tiers):
    - Primary splits from Tier 0 (e.g., "Total Cost of Revenues", "Gross Profit", "Gross Margin") -> Tier 1.
    - Secondary splits from Gross Profit (e.g., "Operating Expenses", "Operating Income") -> Tier 2.
    - Breakdowns of Operating Expenses (e.g., "R&D", "SG&A") are Tier 3 (Source: Operating Expenses -> Target: R&D).
    - Final bottom-line metrics (e.g., "Net Income", "Taxes", "Interest") -> Tier 3 or 4.
    - JSON Direction MUST be: [Source: Aggregator -> Target: Sub-category].

    EXHAUSTIVE BUT FOCUSED:
    Extract every granular revenue stream and expense line item that is explicitly part of the INCOME STATEMENT. Balance the math as closely as the document allows using the MOST RECENT quarter's numbers. Do not use commas or currency symbols in the values.
    
    You MUST respond with a single, valid JSON object containing a "links" array matching this structure:
    {
      "links": [
        {"source": "Granular Revenue A", "source_tier": -2, "target": "Category Aggregator", "target_tier": -1, "value": 500},
        {"source": "Category Aggregator", "source_tier": -1, "target": "Total Revenue", "target_tier": 0, "value": 500},
        {"source": "Total Revenue", "source_tier": 0, "target": "Gross Profit", "target_tier": 1, "value": 200}
      ]
    }
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                # We also reinforce the boundary in the user prompt
                {"role": "user", "content": f"Extract the Income Statement financial flows from the most recent quarter in this text. STRICTLY IGNORE balance sheets and cash flows:\n\n{text}"}
            ],
            model=model_name,
            temperature=0.0, # Keep at 0 for deterministic extraction
            max_tokens=4096,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        raise Exception(f"Extraction failed: {str(e)}")


def extract_text_from_pdf(file_wrapper) -> str:
    """ Extracts raw text from an uploaded PDF file object. """
    reader = PyPDF2.PdfReader(file_wrapper)
    extracted_text = []

    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        page_text = page.extract_text()
        if page_text:
            extracted_text.append(page_text)
    
    return "\n".join(extracted_text)

def clean_extracted_text(text: str) -> str:
    """Removes excessive whitespace and standardizes formatting for the LLM."""
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def generate_sankey_chart(sankey_data: dict):
    """
    Builds a Sankey diagram using dynamic manual coordinate positioning to force a center-origin layout.
    """
    if "links" not in sankey_data:
        raise Exception("Invalid JSON structure.")

    # 1. Gather all unique nodes and their designated tiers
    node_tiers = {}
    for link in sankey_data["links"]:
        node_tiers[link["source"]] = link.get("source_tier", 0)
        node_tiers[link["target"]] = link.get("target_tier", 0)

    list_of_nodes = list(node_tiers.keys())
    node_mapping = {name: idx for idx, name in enumerate(list_of_nodes)}

    # 2. Calculate values for labels
    sum_in = {name: 0 for name in list_of_nodes}
    sum_out = {name: 0 for name in list_of_nodes}
    for link in sankey_data["links"]:
        sum_out[link["source"]] += link.get("value", 0)
        sum_in[link["target"]] += link.get("value", 0)
        
    node_values = {name: max(sum_in[name], sum_out[name]) for name in list_of_nodes}
    formatted_labels = [f"{name}<br>${node_values[name]:,.0f}" for name in list_of_nodes]

    # 3. Dynamic Coordinate Calculation (The Magic)
    # Group nodes by their tier
    tiers = defaultdict(list)
    for name, tier in node_tiers.items():
        tiers[tier].append(name)
        
    # Find the min and max tiers to calculate horizontal spacing (X-axis)
    min_tier = min(tiers.keys())
    max_tier = max(tiers.keys())
    tier_range = max_tier - min_tier if max_tier != min_tier else 1
    
    node_x = [0.0] * len(list_of_nodes)
    node_y = [0.0] * len(list_of_nodes)
    
    for tier, nodes_in_tier in tiers.items():
        # Calculate X position based on tier level (scaled between 0.01 and 0.99)
        # Shift tier so min_tier is at 0
        normalized_tier = tier - min_tier
        x_pos = 0.01 + (normalized_tier / tier_range) * 0.98
        
        # Calculate Y positions to spread nodes evenly in their column
        num_nodes = len(nodes_in_tier)
        for i, name in enumerate(nodes_in_tier):
            idx = node_mapping[name]
            node_x[idx] = x_pos
            # Spread Y evenly between 0.1 and 0.9
            if num_nodes == 1:
                node_y[idx] = 0.5
            else:
                node_y[idx] = 0.1 + (i / (num_nodes - 1)) * 0.8

    # 4. Color Engine
    node_colors = []
    for name in list_of_nodes:
        lower_name = name.lower()
        tier = node_tiers[name]
        
        if tier < 0:
            node_colors.append("#808080") # Dark Grey for incoming revenue
        elif tier == 0:
            node_colors.append("#595959") # Darkest Grey for Center
        elif any(keyword in lower_name for keyword in ["profit", "income", "net"]):
            node_colors.append("#2ca02c") # Green
        elif any(keyword in lower_name for keyword in ["cost", "expense", "tax", "r&d", "sg&a", "loss"]):
            node_colors.append("#d62728") # Red
        else:
            node_colors.append("#a6a6a6") # Fallback

    sources = []
    targets = []
    values = []
    link_colors = []

    for link in sankey_data["links"]:
        sources.append(node_mapping[link["source"]])
        targets.append(node_mapping[link["target"]])
        values.append(link.get("value", 0))
        
        # Color links based on the Right-Side target, or Grey if it's a left-side flow
        if link.get("target_tier", 0) <= 0:
            link_colors.append("rgba(128, 128, 128, 0.3)") # Translucent Grey
        else:
            target_name = link["target"].lower()
            if any(k in target_name for k in ["profit", "income", "net"]):
                link_colors.append("rgba(44, 160, 44, 0.3)")
            elif any(k in target_name for k in ["cost", "expense", "tax", "r&d", "sg&a"]):
                link_colors.append("rgba(214, 39, 40, 0.3)")
            else:
                link_colors.append("rgba(166, 166, 166, 0.3)")

    # 5. Build Plotly Object with Explicit Coordinates
    fig = go.Figure(data=[go.Sankey(
        arrangement="freeform", # Allows explicit coordinate mapping
        node=dict(
            pad=15,
            thickness=30,
            line=dict(color="black", width=0.5),
            label=formatted_labels,
            color=node_colors,
            x=node_x, # Inject our calculated X coordinates
            y=node_y  # Inject our calculated Y coordinates
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors
        )
    )])

    fig.update_layout(
        title_text="Center-Origin Financial Flow Analysis", 
        font_size=12,
        height=650,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    return fig