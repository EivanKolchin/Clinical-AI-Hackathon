import streamlit as st
import os
import glob
from pathlib import Path
from dotenv import load_dotenv, set_key

# Load environment variables
env_path = Path('.env')
load_dotenv(dotenv_path=env_path)

st.set_page_config(page_title="TSPP Clinical Data Extraction", layout="wide")

st.title("TSPP Clinical Data Extraction")
st.markdown("Automated processing of MDT outcome proformas (.docx) for clinical data extraction, patient anonymisation, and structural structuring into verified output records.")

# Sidebar for Settings
with st.sidebar:
    st.header("Configuration")
    st.markdown("Manage system parameters.")
    
    current_key = os.environ.get("GOOGLE_API_KEY", "")
    new_key = st.text_input("Generative AI Service Key", value=current_key, type="password")
    
    if st.button("Save Configuration"):
        if not env_path.exists():
            env_path.touch()
        set_key(str(env_path), "GOOGLE_API_KEY", new_key)
        os.environ["GOOGLE_API_KEY"] = new_key
        st.success("Configuration saved successfully.")
    
    st.divider()
    st.markdown("**System Architecture:**")
    st.markdown("- TSPP Two-Stage Parsing")
    st.markdown("- Generative Structuring")

# Main Interface
st.subheader("1. Clinical Document Upload")
uploaded_file = st.file_uploader("Upload MDT Proforma (.docx)", type=["docx"])

st.subheader("2. Processing Pipeline")
if st.button("Initiate Pipeline", type="primary"):
    if not os.environ.get("GOOGLE_API_KEY"):
        st.error("Please provide the Generative AI Service Key in the Configuration sidebar.")
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
            with st.spinner(f"Processing '{os.path.basename(file_to_process)}' ... (Execution in progress)"):
                # We trap stdout to not clutter console but we could redirect it to UI
                run_pipeline(file_to_process, "output")
                
            st.success("Pipeline execution complete. Clinical data structured and verified.")
            
            # Show results and offer downloads
            st.subheader("3. Export Records")
            excel_files = glob.glob("output/excel/*.xlsx")
            if excel_files:
                latest_excel = max(excel_files, key=os.path.getctime)
                with open(latest_excel, "rb") as f:
                    st.download_button(
                        label="Download Structured Output (Excel)",
                        data=f,
                        file_name=os.path.basename(latest_excel),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.warning("No Excel manifest constructed. Review systemic logs for stage 2/3 faults.")
                
            # Offer latest JSON zip downloading if needed
            json_files = glob.glob("output/json/*.json")
            if json_files:
                st.markdown(f"*{len(json_files)} intermediate structural components assembled.*")
                
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")
