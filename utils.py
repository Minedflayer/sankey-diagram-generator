# utils.py
import json
import re
import PyPDF2
from groq import Groq
import streamlit as st
import plotly.graph_objects as go
from collections import defaultdict

def get_groq_client():
    """ Initializes Groq client using streamlit native secrets. """
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

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
    Forces the LLM to extract data into a strict recursive tree structure,
    making it bulletproof for ANY company's financial report.
    """
    client = get_groq_client()

    system_prompt = """
    You are an expert forensic financial analyst. Extract data from the INCOME STATEMENT into a strict RECURSIVE JSON tree structure.
    
    You MUST respond with a JSON object containing exactly TWO root trees: "revenues_tree" and "expenses_and_profits_tree".
    
    SCHEMA STRUCTURE:
    Every node in the tree MUST have:
    - "name": The string name of the line item.
    - "value": The numerical value (NO commas or currency symbols).
    - "breakdown": An array of sub-nodes (only if the item is broken down further).

    CRITICAL REVENUE RULES:
    - The root "name" of the revenues_tree MUST be exactly "Total Revenue".
    - Populate its "breakdown" with the nested revenue streams.

    CRITICAL EXPENSE & PROFIT RULES:
    - The root "name" of the expenses_and_profits_tree MUST be exactly "Total Revenue".
    - Populate its "breakdown" with the immediate splits (e.g., "Total Cost of Revenues" and "Gross Profit").
    - Continue breaking those down (e.g., Gross Profit breaks down into "Operating Expenses" and "Operating Income").
    - Operating Expenses breaks down into "R&D", "SG&A", etc.

    NAMING RULE (PREVENT MERGING):
    If a revenue line and a cost line share the exact same name, append the word "Revenue" or "Cost" to make them unique. 

    BOUNDARIES:
    - IGNORE Balance Sheets (Assets/Liabilities) and Cash Flows.
    - Use EXACT numbers from the MOST RECENT quarter.
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract the recursive Income Statement hierarchy from this text:\n\n{text}"}
            ],
            model=model_name,
            temperature=0.0, # Zero creativity, pure data extraction
            max_tokens=8000,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        raise Exception(f"Extraction failed: {str(e)}")

def generate_sankey_chart(sankey_data: dict):
    """
    Recursively parses the JSON tree to build perfect graph links,
    calculates spatial tiers, and renders the center-origin diagram.
    """
    clean_links = []

    # 1. Recursive Parsers
    def parse_revenues(node):
        """Revenues flow IN to their parents (Child -> Parent)"""
        if "breakdown" in node and isinstance(node["breakdown"], list):
            for child in node["breakdown"]:
                val = float(str(child.get("value", 0)).replace(",", "").replace("$", ""))
                if val > 0:
                    clean_links.append({
                        "source": child["name"].strip(),
                        "target": node["name"].strip(),
                        "value": val
                    })
                    parse_revenues(child)

    def parse_expenses(node, current_parent):
        """Expenses and Profits flow OUT of their parents (Parent -> Child)"""
        if "breakdown" in node and isinstance(node["breakdown"], list):
            for child in node["breakdown"]:
                val = float(str(child.get("value", 0)).replace(",", "").replace("$", ""))
                if val > 0:
                    clean_links.append({
                        "source": current_parent.strip(),
                        "target": child["name"].strip(),
                        "value": val
                    })
                    parse_expenses(child, child["name"].strip())

    # Safely execute the parsing
    if "revenues_tree" in sankey_data:
        parse_revenues(sankey_data["revenues_tree"])
        
    if "expenses_and_profits_tree" in sankey_data:
        parse_expenses(sankey_data["expenses_and_profits_tree"], "Total Revenue")

    if not clean_links:
        raise Exception("The AI failed to extract valid links. Please try again.")

    # 2. Graph Traversal: Auto-assign Tiers based on distance from "Total Revenue"
    node_tiers = {"Total Revenue": 0}
    
    # Positive Tiers (Flowing OUT)
    changed = True
    while changed:
        changed = False
        for link in clean_links:
            if link["source"] in node_tiers and link["target"] not in node_tiers:
                node_tiers[link["target"]] = node_tiers[link["source"]] + 1
                changed = True

    # Negative Tiers (Flowing IN)
    changed = True
    while changed:
        changed = False
        for link in clean_links:
            if link["target"] in node_tiers and link["source"] not in node_tiers:
                node_tiers[link["source"]] = node_tiers[link["target"]] - 1
                changed = True
                
    # Fallback for disconnected nodes
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
            thickness=30,  # Sleek, thin vertical nodes
            line=dict(color="black", width=0.5),
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
        height=700,
        margin=dict(l=20, r=20, t=150, b=150) # Crushes the graph into the middle to create white space
    )
    
    return fig