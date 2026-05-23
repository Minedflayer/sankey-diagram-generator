# utils.py
import json
import re
from groq import Groq
import streamlit as st
import fitz  # PyMuPDF
import plotly.graph_objects as go
from collections import defaultdict
from prompt import INCOME_STATEMENT_EXTRACTION_PROMPT

@st.cache_resource
def get_groq_client():
    """ Initializes Groq client using streamlit native secrets. """
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

def extract_text_from_pdf(file_wrapper) -> str:
    """ Extracts raw text from an uploaded PDF file object using PyMuPDF. """
    # Reset the stream position in case it was read elsewhere in the app
    file_wrapper.seek(0)
    file_bytes = file_wrapper.read()
    
    # Open the PDF from the memory buffer
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    extracted_text = []

    for page in doc:
        # get_text("text") attempts to preserve the visual layout of tables
        page_text = page.get_text("text") 
        if page_text:
            extracted_text.append(page_text)
            
    doc.close()
    return "\n".join(extracted_text)

def clean_extracted_text(text: str) -> str:
    """Removes excessive whitespace and standardizes formatting for the LLM."""
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def extract_data(text: str, model_name: str, temperature: float) -> dict:
    """
    Forces the LLM to extract data into a STRICT predefined accounting skeleton,
    and explicitly forbids unit conversion to prevent zero-dropping hallucinations.
    """
    client = get_groq_client()

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": INCOME_STATEMENT_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Extract the Income Statement hierarchy from this text using the strict accounting skeleton provided:\n\n{text}"}
            ],
            model=model_name,
            temperature=0.0, # Zero creativity, pure data extraction
            max_tokens=8000,
            response_format={"type": "json_object"}
        )

        raw_content = response.choices[0].message.content.strip()
        cleaned_content = re.sub(r"```(?:json)?|```", "", raw_content).strip()

        return json.loads(cleaned_content)
    except Exception as e:
        raise Exception(f"Extraction failed: {str(e)}")
    
    # --- Rendering Helper Functions --

def _clean_financial_value(val) -> float:
    """Standardizes numeric extraction logic."""
    return float(str(val).replace(",", "").replace("$", ""))

def _parse_json_to_edges(sankey_data: dict) -> list:
    """
    Recursively parses the JSON tree to build perfect graph links,
    uses hidden name-spacing to prevent node collision,
    calculates spatial tiers, and renders the center-origin diagram.
    """
    clean_links = []
    def parse_revenues(node):
        """Revenues flow IN to their parents (Child -> Parent)"""
        if "breakdown" in node and isinstance(node["breakdown"], list):
            for child in node["breakdown"]:
                val = float(str(child.get("value", 0)).replace(",", "").replace("$", ""))
                if val > 0:
                    source_name = child["name"].strip()
                    target_name = node["name"].strip()
                    
                    # Secretly tag left-side nodes to prevent merging
                    if source_name.lower() != "total revenue": source_name += " [IN]"
                    if target_name.lower() != "total revenue": target_name += " [IN]"

                    clean_links.append({
                        "source": source_name,
                        "target": target_name,
                        "value": val
                    })
                    parse_revenues(child)
    

    
    def parse_expenses(node, current_parent):
        if "breakdown" in node and isinstance(node["breakdown"], list):
            for child in node["breakdown"]:
                val = _clean_financial_value(child.get("value", 0))
                if val > 0:
                    source_name = current_parent.strip()
                    target_name = child["name"].strip()
                    
                    if source_name.lower() != "total revenue": source_name += " [OUT]"
                    if target_name.lower() != "total revenue": target_name += " [OUT]"

                    clean_links.append({"source": source_name, "target": target_name, "value": val})
                    parse_expenses(child, child["name"].strip())
    
    if "revenues_tree" in sankey_data:
        parse_revenues(sankey_data["revenues_tree"])
        
    if "expenses_and_profits_tree" in sankey_data:
        parse_expenses(sankey_data["expenses_and_profits_tree"], "Total Revenue")

    if not clean_links:
        raise Exception("The AI failed to extract valid links. Please try again.")
        
    return clean_links

def _compute_node_tiers(clean_links: list) -> dict:
    """Traverses the graph to assign spatial tiers based on distance from Total Revenue."""
    node_tiers = {"Total Revenue": 0}
    max_iterations = len(clean_links) * 2 # Prevent infinite loops from LLM hallucinations
    
    # Calculate downstream tiers
    changed = True
    iteration = 0
    while changed and iteration < max_iterations:
        changed = False
        for link in clean_links:
            if link["source"] in node_tiers and link["target"] not in node_tiers:
                node_tiers[link["target"]] = node_tiers[link["source"]] + 1
                changed = True
        iteration += 1

    # Calculate upstream tiers
    changed = True
    iteration = 0
    while changed and iteration < max_iterations:
        changed = False
        for link in clean_links:
            if link["target"] in node_tiers and link["source"] not in node_tiers:
                node_tiers[link["source"]] = node_tiers[link["target"]] - 1
                changed = True
        iteration += 1
        
    # Catch any disconnected components
    for link in clean_links:
        if link["source"] not in node_tiers: node_tiers[link["source"]] = -1
        if link["target"] not in node_tiers: node_tiers[link["target"]] = 1
        
    return node_tiers
def _build_sankey_figure(clean_links: list, node_tiers: dict) -> go.Figure:
    """Handles the aesthetic calculation and Plotly object generation."""
    list_of_nodes = sorted(list(node_tiers.keys()))
    node_mapping = {name: idx for idx, name in enumerate(list_of_nodes)}

    # Calculate Values
    sum_in = {name: 0 for name in list_of_nodes}
    sum_out = {name: 0 for name in list_of_nodes}
    for link in clean_links:
        sum_out[link["source"]] += link["value"]
        sum_in[link["target"]] += link["value"]
        
    node_values = {name: max(sum_in[name], sum_out[name]) for name in list_of_nodes}
    
    # Format Labels
    formatted_labels = []
    for name in list_of_nodes:
        display_name = name.replace(" [IN]", "").replace(" [OUT]", "")
        formatted_labels.append(f"{display_name}<br>${node_values[name]:,.0f}M")

    # Dynamic Coordinate Calculation
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

    # Semantic & Structural Color Engine
    node_colors = []
    for name in list_of_nodes:
        clean_name = name.replace(" [IN]", "").replace(" [OUT]", "").lower()
        tier = node_tiers[name]
        
        if tier < 0:
            node_colors.append("#808080")
        elif tier == 0:
            node_colors.append("#404040")
        elif tier > 0:
            if any(k in clean_name for k in ["profit", "income", "net", "margin"]):
                node_colors.append("#2ca02c")
            else:
                node_colors.append("#d62728")

    # Mapping sources and targets
    sources, targets, values, link_colors = [], [], [], []
    for link in clean_links:
        sources.append(node_mapping[link["source"]])
        targets.append(node_mapping[link["target"]])
        values.append(link["value"])
        
        target_tier = node_tiers[link["target"]]
        
        if target_tier <= 0:
            link_colors.append("rgba(128, 128, 128, 0.3)")
        else:
            clean_target = link["target"].replace(" [IN]", "").replace(" [OUT]", "").lower()
            if any(k in clean_target for k in ["profit", "income", "net", "margin"]):
                link_colors.append("rgba(44, 160, 44, 0.3)")
            else:
                link_colors.append("rgba(214, 39, 40, 0.3)")

    # Build the Plotly Object
    fig = go.Figure(data=[go.Sankey(
        arrangement="freeform",
        textfont=dict(color="black", size=12),
        node=dict(
            pad=25,
            thickness=10,
            line=dict(color="black", width=0.5),
            label=formatted_labels,
            color=node_colors,
            x=node_x,
            y=node_y,
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
        margin=dict(l=20, r=20, t=150, b=150)
    )
    
    return fig

def generate_sankey_chart(sankey_data: dict) -> go.Figure:
    """Orchestrates the creation of the Sankey diagram by calling dedicated helper functions."""
    edges = _parse_json_to_edges(sankey_data)
    tiers = _compute_node_tiers(edges)
    return _build_sankey_figure(edges, tiers)