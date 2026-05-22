# app.py
import streamlit as st
# Import our new extraction utilities
from utils import extract_text_from_pdf, clean_extracted_text, extract_data, generate_sankey_chart

# Application Configuration
st.set_page_config(
    page_title="AI Sankey Diagram Generator",
    page_icon="📊",
    layout="wide"
)

st.title = ("Sankey Diagram Generator")
st.markdown(
    """ Extract unstructured financial data from documents and transform it into 
    structured interactive Sankey flows using LLM semantic parsing.  """
)

st.sidebar.header("Model configuration")

model_options = [
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "mixtral-8x7b-32768"
]
selected_model = st.sidebar.selectbox(
    "Select LLM Architecture",
    options=model_options,
    index=0
)

# Hyperparameters
temperature = st.sidebar.slider (
    "Temperature (Creativity)",
    min_value=0.0,
    max_value=1.0,
    value=0.1,
    step=0.05,
    help="Lower values yield deterministic structural extraction."
)

st.sidebar.divider()
st.sidebar.info("Phase 2 Environment Target: Active")

# Main Content Area: Document Processing Core
st.subheader("Data input")
uploaded_file = st.file_uploader(
    "Upload financial document",
    type=["pdf", "txt"],
    help="Accepts plaintext files or standardized PDFs containing financial statements."

)


# Procesing pipeline trigger
if uploaded_file is not None:
    with st.spinner("Extracting text from document..."):
        if uploaded_file.name.endswith('.pdf'):
            raw_text = extract_text_from_pdf(uploaded_file)
        else:
            # Handles standard text file format
            raw_text = uploaded_file.read().decode("utf-8")
        # Run cleaning rules
        cleaned_text = clean_extracted_text(raw_text)
        
    if cleaned_text:
        st.success(f"Successfully processed: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Characters", len(cleaned_text))
        with col2:
            st.metric("Estimated Word Count", len(cleaned_text.split()))
            
        with st.expander("Preview Extracted Clean Text Data"):
            st.text_area("Document Content", cleaned_text, height=200, disabled=True)
            
        st.session_state['document_text'] = cleaned_text
        
        st.markdown("---")
        st.subheader("AI Analysis & Relation Mapping")
        
        # Trigger button for LLM generation phase
        if st.button("Generate Structured Flow Blueprint", type="primary"):
            with st.spinner("Analyzing data layout and balancing cash flows via Groq API..."):
                try:
                  
                    # Fire API request to Groq network
                    sankey_data = extract_data(
                        text=st.session_state['document_text'],
                        model_name=selected_model,
                        temperature=temperature
                    )
                    
                    # Store data safely for visualization in Phase 4
                    st.session_state['sankey_data'] = sankey_data
                    st.success("Successfully isolated financial flow layers!")

           
                    st.markdown("---")
                    st.subheader("Interactive Visualization")
                    
                    # Generate and render the Plotly object
                    fig = generate_sankey_chart(sankey_data)
                    st.plotly_chart(fig, use_container_width=True)
                    # -------------------------------
                    
                    with st.expander("View Raw Structural Blueprint JSON"):
                        st.json(sankey_data)
                    
                except Exception as error:
                    st.error(f"Execution pipeline halted: {str(error)}")
                    
    else:
        st.error("Document appears to be empty or unreadable.")
else:
    st.info("Awaiting file upload to initiate extraction pipeline.")  

# Placeholder Execution Pipeline Verification
if uploaded_file is not None:
    st.success(f"File successfully staged: {uploaded_file.name}")

    # Context Metadata Display
    file_details = {
        "Filename": uploaded_file.name,
        "FileType": uploaded_file.type,
        "FileSize": f"{uploaded_file.size / 1024:.2f} KB"
    }
    st.json(file_details)
else:
    st.info("Awaiting file upload to initiate extraction pipeline.")