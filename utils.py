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
    Instructs the LLM to extract financial data strictly from the Income Statement, 
    enforcing unique node naming and the Golden Accounting Equation.
    """
    client = get_groq_client()

    system_prompt = """
    You are an expert forensic financial analyst. Your job is to extract hierarchical financial flow data ONLY from the INCOME STATEMENT (Statement of Operations) to build a Center-Origin Sankey diagram.
    
    CRITICAL BOUNDARY RULES (WHAT TO IGNORE):
    1. ONLY extract revenues, costs of revenue, gross profit, operating expenses, and net income.
    2. STRICTLY IGNORE Balance Sheet items and Cash Flow statement items.

    CRITICAL NODE NAMING RULE (PREVENT MERGING):
    If a revenue line and a cost line share the exact same name in the document (e.g., "Energy generation and storage"), you MUST append the word "Revenue" or "Cost" to distinguish them (e.g., "Energy generation and storage Revenue" and "Energy generation and storage Cost"). Node names MUST be unique!
    
    CRITICAL TIER RULES:
    The central node representing the total incoming money (e.g., "Total revenues") is ALWAYS Tier 0.
    
    LEFT SIDE (INCOMING REVENUES - Negative Tiers):
    - Lowest-level sub-categories -> Tier -2 or -3.
    - Mid-level aggregators -> Tier -1.
    - JSON Direction MUST be: [Source: Sub-category -> Target: Aggregator or Tier 0].
    
    RIGHT SIDE (OUTGOING COSTS/PROFITS - Positive Tiers):
    - THE GOLDEN RULE: Tier 0 ("Total revenues") MUST split into EXACTLY two Tier 1 nodes: "Total cost of revenues" and "Gross profit".
    - "Total cost of revenues" (Tier 1) MUST split into its granular cost sub-categories (Tier 2). JSON Direction: [Source: "Total cost of revenues" -> Target: "Specific Cost"].
    - "Gross profit" (Tier 1) MUST split into "Operating expenses" (Tier 2) and "Income from operations" (Tier 2).
    - Breakdowns of "Operating expenses" (e.g., "R&D", "SG&A") are Tier 3.
    - Final bottom-line metrics (e.g., "Net income", "Taxes") are Tier 3.
    - JSON Direction MUST be: [Source: Aggregator -> Target: Sub-category].

    EXHAUSTIVE BUT FOCUSED:
    Extract every granular revenue stream and expense line item that is explicitly part of the INCOME STATEMENT. Balance the math as closely as the document allows using the MOST RECENT quarter's numbers (Q1-2026). Do not use commas or currency symbols in the values.
    
    You MUST respond with a single, valid JSON object containing a "links" array matching this structure:
    {
      "links": [
        {"source": "Granular Revenue A", "source_tier": -2, "target": "Category Aggregator", "target_tier": -1, "value": 500},
        {"source": "Total revenues", "source_tier": 0, "target": "Total cost of revenues", "target_tier": 1, "value": 300}
      ]
    }
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract the Income Statement financial flows from the most recent quarter in this text. STRICTLY IGNORE balance sheets and cash flows:\n\n{text}"}
            ],
            model=model_name,
            temperature=0.0,
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


def extract_data(text: str, model_name: str, temperature: float) -> dict:
    """
    Forces the LLM to isolate incoming and outgoing funds into separate arrays, 
    preventing cross-wiring hallucinations.
    """
    client = get_groq_client()

    system_prompt = """
    You are an expert forensic financial analyst. Extract data from the INCOME STATEMENT into a strict JSON format to build a Center-Origin Sankey diagram.
    
    CRITICAL RULE: The central anchor node MUST be named EXACTLY "Total Revenue".

    You MUST respond with a JSON object containing TWO separate arrays: "revenue_streams" and "expenses_and_profits".

    ARRAY 1: "revenue_streams" (Incoming Money)
    - Map sub-revenues to category revenues, and category revenues to "Total Revenue".
    - Target nodes in this array MUST eventually roll up to "Total Revenue".
    - Example: {"source": "Auto Sales", "target": "Total Revenue", "value": 15473}
    
    ARRAY 2: "expenses_and_profits" (Outgoing Money)
    - "Total Revenue" MUST be the source that splits into "Cost of Revenue" and "Gross Profit".
    - "Cost of Revenue" splits into granular costs (e.g., {"source": "Cost of Revenue", "target": "Auto Costs", "value": 12812}).
    - "Gross Profit" splits into "Operating Expenses" and "Operating Profit".
    - "Operating Expenses" splits into R&D, SG&A, etc.
    
    STRICT BOUNDARIES:
    - IGNORE Balance Sheets (Assets, Liabilities, Equity) and Cash Flows.
    - NEVER link a specific revenue directly to a specific cost. Everything must pass through "Total Revenue".
    - Use exact numerical values (no commas or currency symbols).
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract the Income Statement financial flows from this text. STRICTLY IGNORE balance sheets and cash flows:\n\n{text}"}
            ],
            model=model_name,
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        raise Exception(f"Extraction failed: {str(e)}")

def generate_sankey_chart(sankey_data: dict):
    """
    Uses a graph traversal algorithm to automatically anchor the network to 'Total Revenue'
    and dynamically calculate spatial tiers.
    """
    # 1. Merge the isolated arrays into a single clean list
    raw_links = sankey_data.get("revenue_streams", []) + sankey_data.get("expenses_and_profits", [])
    
    clean_links = []
    for link in raw_links:
        if not isinstance(link, dict): continue
        source = str(link.get("source", "Unknown")).strip()
        target = str(link.get("target", "Unknown")).strip()
        
        raw_val = str(link.get("value", 0)).replace(",", "").replace("$", "").replace(" ", "")
        try:
            value = float(raw_val)
        except ValueError:
            value = 0.0
            
        clean_links.append({"source": source, "target": target, "value": value})

    # 2. Graph Traversal: Auto-assign Tiers based on distance from "Total Revenue"
    node_tiers = {"Total Revenue": 0}
    
    # Calculate positive tiers (flowing OUT of Total Revenue)
    changed = True
    while changed:
        changed = False
        for link in clean_links:
            if link["source"] in node_tiers and link["target"] not in node_tiers:
                node_tiers[link["target"]] = node_tiers[link["source"]] + 1
                changed = True

    # Calculate negative tiers (flowing IN to Total Revenue)
    changed = True
    while changed:
        changed = False
        for link in clean_links:
            if link["target"] in node_tiers and link["source"] not in node_tiers:
                node_tiers[link["source"]] = node_tiers[link["target"]] - 1
                changed = True
                
    # Fallback for disconnected hallucinated nodes
    for link in clean_links:
        if link["source"] not in node_tiers: node_tiers[link["source"]] = -1
        if link["target"] not in node_tiers: node_tiers[link["target"]] = 1

    # 3. Build Nodes and Values
    list_of_nodes = sorted(list(node_tiers.keys()))
    node_mapping = {name: idx for idx, name in enumerate(list_of_nodes)}

    sum_in = {name: 0 for name in list_of_nodes}
    sum_out = {name: 0 for name in list_of_nodes}
    for link in clean_links:
        sum_out[link["source"]] += link["value"]
        sum_in[link["target"]] += link["value"]
        
    node_values = {name: max(sum_in[name], sum_out[name]) for name in list_of_nodes}
    formatted_labels = [f"{name}<br>${node_values[name]:,.0f}" for name in list_of_nodes]

    # 4. Dynamic Coordinate Calculation
    tiers = defaultdict(list)
    for name, tier in node_tiers.items():
        tiers[tier].append(name)
        
    min_tier = min(tiers.keys())
    max_tier = max(tiers.keys())
    tier_range = max_tier - min_tier if max_tier != min_tier else 1
    
    node_x = [0.0] * len(list_of_nodes)
    node_y = [0.0] * len(list_of_nodes)
    
    for tier, nodes_in_tier in tiers.items():
        normalized_tier = tier - min_tier
        x_pos = 0.01 + (normalized_tier / tier_range) * 0.98
        
        num_nodes = len(nodes_in_tier)
        for i, name in enumerate(nodes_in_tier):
            idx = node_mapping[name]
            node_x[idx] = x_pos
            if num_nodes == 1:
                node_y[idx] = 0.5
            else:
                node_y[idx] = 0.1 + (i / (num_nodes - 1)) * 0.8

    # 5. Semantic Color Engine
    node_colors = []
    for name in list_of_nodes:
        lower_name = name.lower()
        tier = node_tiers[name]
        
        if tier < 0:
            node_colors.append("#808080") # Grey for revenues
        elif tier == 0:
            node_colors.append("#404040") # Dark Grey for Total Revenue Hub
        elif any(k in lower_name for k in ["profit", "income", "net"]):
            node_colors.append("#2ca02c") # Green
        elif any(k in lower_name for k in ["cost", "expense", "tax", "r&d", "sg&a", "loss"]):
            node_colors.append("#d62728") # Red
        else:
            node_colors.append("#a6a6a6")

    sources, targets, values, link_colors = [], [], [], []
    for link in clean_links:
        sources.append(node_mapping[link["source"]])
        targets.append(node_mapping[link["target"]])
        values.append(link["value"])
        
        if node_tiers[link["target"]] <= 0:
            link_colors.append("rgba(128, 128, 128, 0.3)")
        else:
            target_name = link["target"].lower()
            if any(k in target_name for k in ["profit", "income", "net"]):
                link_colors.append("rgba(44, 160, 44, 0.3)")
            elif any(k in target_name for k in ["cost", "expense", "tax", "r&d", "sg&a"]):
                link_colors.append("rgba(214, 39, 40, 0.3)")
            else:
                link_colors.append("rgba(166, 166, 166, 0.3)")

    # 6. Build the Plotly Object
    fig = go.Figure(data=[go.Sankey(
        arrangement="freeform",
        node=dict(
            pad=15,
            thickness=30,
            line=dict(color="black", width=0.3),
            label=formatted_labels,
            color=node_colors,
            x=node_x,
            y=node_y
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
        height=700,  # Keep the canvas itself tall
        # Crank up the top (t) and bottom (b) margins to compress the chart!
        margin=dict(l=20, r=20, t=150, b=150) 
    )
    return fig