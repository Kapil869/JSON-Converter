import streamlit as st
import pandas as pd
import json
from datetime import datetime
import io
import zipfile

st.set_page_config(page_title="Logistics JSON Master Suite", layout="wide")

# --- Helper Functions ---
def format_date(date_val):
    """Converts various date formats to ISO 8601 format required for JSON."""
    try:
        if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).lower() == "nat":
            return ""
        # Handles DD.MM.YYYY or DD/MM/YYYY using dayfirst=True
        dt = pd.to_datetime(date_val, dayfirst=True)
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')
    except:
        return ""

def clean_val(val):
    """Cleans numeric strings, removes .0 decimals and handles IGM slash formats."""
    if pd.isna(val) or str(val).strip() == "":
        return ""
    s = str(val).strip()
    # Remove IGM year suffix if present (e.g., 3007537/26 -> 3007537)
    if "/" in s:
        s = s.split("/")[0]
    # Remove .0 if the value was read as a float
    if s.endswith(".0"):
        s = s[:-2]
    return s

# --- UI Layout ---
st.title("📦 Logistics JSON Master Suite")
st.sidebar.header("Service Selection")

# User selects the type of filing
service = st.sidebar.radio("Select Filing Type:", ["TP Filing", "CTM Filing"], key="service_choice")

uploaded_file = st.file_uploader(f"Upload Excel File for {service}", type="xlsx", key=f"up_{service}")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        
        col1, col2 = st.columns(2)
        with col1:
            sheet = st.selectbox("Select Sheet Name:", xl.sheet_names, key=f"sh_{service}")
        with col2:
            # Manual Header Index to avoid errors if the Excel layout changes
            h_row = st.number_input("Header Row Index (Start from 0):", min_value=0, value=2, key=f"hr_{service}")

        # Load and clean the data
        df = pd.read_excel(uploaded_file, sheet_name=sheet, header=h_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')

        json_files = {}

        # ---------------------------------------------------------
        # LOGIC 1: TP FILING (Groups data by JOB NO.)
        # ---------------------------------------------------------
        if service == "TP Filing":
            job_col = 'JOB NO.' if 'JOB NO.' in df.columns else 'JOB NO. '
            if job_col in df.columns:
                df[job_col] = df[job_col].ffill() # Handle merged cells for Job numbers
                for job_id, group in df.groupby(job_col):
                    first_row = group.iloc[0]
                    clean_id = str(job_id).replace("SINGLE ", "").replace(" ", "").replace(".0", "")
                    
                    tp_template = {
                        "webFormId": "", "webFormTypeId": "24", "icegateId": "INDIGOCARGO",
                        "thumbPrint": "15 58 d8 6a 4e 61 5a e3 32 2c 5c 78 4a 3e d4 4e 09 0e 6a 76",
                        "serialNumber": "0a 8e 97 45 d6 5d", "roleId": 7, "url": "igm-egm/air-atp",
                        "atsStep1": {
                            "message_type": "F", "unique_job_id": clean_id,
                            "custom_house_code": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "port_destination": "INMAA4", "transhipment_Agency_Type": "DA", 
                            "transhipment_Agency_Code": "6E", "gateway_Custodian_Code": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_Transport": "A", "airline_Code": "6E", "carrier_Code": "AABCI2726B",
                            "flight_Number": str(first_row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(first_row.get('FLIGHT DATE')), "bond_Port": clean_val(first_row.get('BOND PORT', 'INCCU4'))
                        },
                        "atsStep2": { "lineDetails": [], "truckDetails": [] }
                    }
                    for _, row in group.iterrows():
                        mawb = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "").replace(".0", "")
                        tp_template["atsStep2"]["lineDetails"].append({
                            "cargo_Transfer_Manifestno": clean_val(row.get('CTM NO')),
                            "cargo_Transfer_Manifestdate": format_date(row.get('CTM DATE')),
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "consignment_Value_INR": clean_val(row.get('VALUE', 0))
                        })
                        tp_template["atsStep2"]["truckDetails"].append({
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "truck_Number": "", "seal_Number": "",
                            "flight_Number": str(row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(row.get('FLIGHT DATE'))
                        })
                    json_files[f"{clean_id}_TP.json"] = json.dumps(tp_template, indent=2)

        # ---------------------------------------------------------
        # LOGIC 2: CTM FILING (Groups data by IGM Number)
        # ---------------------------------------------------------
        elif service == "CTM Filing":
            if 'IGM' in df.columns:
                df['IGM'] = df['IGM'].ffill() # Handle merged cells for IGM numbers
                for igm_id, group in df.groupby('IGM'):
                    first_row = group.iloc[0]
                    clean_igm = clean_val(igm_id)
                    
                    ctm_template = {
                        "webFormId": "", "webFormTypeId": "21", "icegateId": "INDIGOCARGO",
                        "roleId": 7, "url": "igm-egm/ctm-webform",
                        "freshCTMStep1": {
                            "messageType": "F", "customsHouseCode": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "fileName": f"CTM_{clean_igm}", "iGMNumber": clean_igm,
                            "AirlineCode": "6E", "iGMDate": format_date(first_row.get('IGM DATE')),
                            "portofDestination": "INMAA4", "GatewayCustodianCode": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_of_transport": "ACC"
                        },
                        "freshCTMStep2": { "line_details": [] }
                    }
                    for _, row in group.iterrows():
                        mawb = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "").replace(".0", "")
                        ctm_template["freshCTMStep2"]["line_details"].append({
                            "customsHouseCode": clean_val(row.get('BOND PORT', 'INCCU4')),
                            "masterAirwayBillNumber": mawb, "houseAirwayBillNumber": ""
                        })
                    json_files[f"IGM_{clean_igm}_CTM.json"] = json.dumps(ctm_template, indent=2)

        # --- ZIP File Generation ---
        if json_files:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f_name, content in json_files.items():
                    zip_file.writestr(f_name, content)
            
            st.divider()
            st.success(f"Processing Complete: {len(json_files)} file(s) generated.")
            st.download_button(
                label=f"📥 DOWNLOAD {service.upper()} ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"{service.replace(' ', '_')}_Export.zip",
                mime="application/zip",
                key=f"final_btn_{service}"
            )
        else:
            st.error("Grouping column ('JOB NO.' or 'IGM') not found. Please verify the Header Row Index and Sheet selection.")

    except Exception as e:
        st.error(f"Error occurred: {e}")