import streamlit as st
import os
import glob
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv, set_key
import sys
import io

# Load environment variables
env_path = Path('.env')
load_dotenv(dotenv_path=env_path)

st.set_page_config(page_title="Clinical Data Extraction", layout="wide", initial_sidebar_state="expanded")

# Clean aesthetic CSS injection to remove default streamlit cruft (Hamburger menu, running man, footers)
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stDeployButton {display:none;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("Clinical Data Extraction Pipeline")
st.markdown(
    "Automated processing of MDT outcome proformas for data extraction, patient anonymisation, "
    "and formatting into structured output records."
)

class StreamlitRedirect(io.StringIO):
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.accumulated_output = []
        super().__init__()

    def write(self, string):
        if string.strip():
            self.accumulated_output.append(string.strip())
            # Keep only the last 15 lines so it looks like a clean sliding terminal
            display_text = "\n".join(self.accumulated_output[-15:])
            self.placeholder.code(display_text, language="bash")
        return len(string)

    def flush(self):
        pass

# Sidebar for Settings
with st.sidebar:
    st.header("Configuration")
    st.markdown("Manage system parameters.")
    
    current_key = os.environ.get("GOOGLE_API_KEY", "")
    new_key = st.text_input("System Access Key", value=current_key, type="password")
    
    if st.button("Save Configuration"):
        if not env_path.exists():
            env_path.touch()
        set_key(str(env_path), "GOOGLE_API_KEY", new_key)
        os.environ["GOOGLE_API_KEY"] = new_key
        st.success("Configuration saved successfully.")
    
    st.divider()
    st.markdown("**System Architecture:**")
    st.markdown("- Clinical Text Analysis")
    st.markdown("- Automated Data Structuring")

# Main Interface
st.subheader("1. Clinical Document Upload")
uploaded_file = st.file_uploader("Upload MDT Proforma (.docx)", type=["docx"])

st.subheader("2. Processing Pipeline")
if st.button("Initiate Pipeline", type="primary"):
    if not os.environ.get("GOOGLE_API_KEY"):
        st.error("Please provide the System Access Key in the Configuration sidebar.")
    elif uploaded_file is None:
        # Check if default file exists
        default_file = Path("data/hackathon-mdt-outcome-proformas.docx")
        if default_file.exists():
            st.info(f"No file uploaded. Proceeding with system default: '{default_file.name}'")
            file_to_process = str(default_file)
        else:
            st.error("Please upload a .docx document to proceed.")
            st.stop()
    else:
        # Save uploaded file
        os.makedirs("data", exist_ok=True)
        file_path = os.path.join("data", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_to_process = file_path

    if 'file_to_process' in locals():
        os.makedirs("output", exist_ok=True)
        
        # Run the backend logic
        import sys
        
        # Add src to Python path if needed
        src_path = os.path.join(os.path.dirname(__file__), "src")
        if src_path not in sys.path:
            sys.path.append(src_path)
            
        from src.main import main as run_pipeline
        
        try:
            with st.spinner(f"Processing '{os.path.basename(file_to_process)}' ..."):
                
                # Setup a clean visual container for progress logs
                st.markdown("### Execution Log")
                progress_placeholder = st.empty()
                progress_placeholder.code("Initializing Pipeline...", language="bash")
                
                # Redirect stdout to our custom streaming widget
                old_stdout = sys.stdout
                sys.stdout = StreamlitRedirect(progress_placeholder)
                
                try:
                    run_pipeline(file_to_process, "output")
                finally:
                    # Restore original stdout
                    sys.stdout = old_stdout
                
            st.success("Pipeline execution complete. Clinical data structured and verified.")
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

st.divider()

# ----------------- ALWAYS SHOW EXPORT RECORDS SECTION -----------------
st.subheader("3. Export Records")
excel_files = glob.glob("output/excel/*.xlsx")
if excel_files:
    latest_excel = max(excel_files, key=os.path.getctime)
    col_a, col_b = st.columns([1, 1])
    with col_a:
        with open(latest_excel, "rb") as f:
            st.download_button(
                label="Download Structured Output (Excel)",
                data=f,
                file_name=os.path.basename(latest_excel),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    with col_b:
        with st.expander("Preview Latest Excel Document"):
            try:
                df_preview = pd.read_excel(latest_excel, sheet_name="MDT Data")
                st.dataframe(df_preview, use_container_width=True, height=520)
            except Exception as preview_err:
                st.error(f"Could not load preview: {preview_err}")
                
    # Offer latest JSON zip downloading if needed
    json_files = glob.glob("output/json/*.json")
    if json_files:
        st.markdown(f"*{len(json_files)} internal processing files created in `/output/json`.*")
else:
    st.info("No output file found. Please run the pipeline to generate records.")
