import streamlit as st
import pandas as pd
import json
from datetime import datetime
import io
import zipfile

st.set_page_config(page_title="Logistics Master Suite", layout="wide")

# --- Helper Functions ---
def format_date(date_val):
    try:
        if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).lower() == "nat":
            return ""
        dt = pd.to_datetime(date_val, dayfirst=True)
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')
    except:
        return ""

def clean_val(val):
    if pd.isna(val) or str(val).strip() == "":
        return ""
    s = str(val).strip()
    if "/" in s:
        s = s.split("/")[0]
    if s.endswith(".0"):
        s = s[:-2]
    return s

# --- UI ---
st.title("📦 Logistics Master Suite")
st.sidebar.header("Service Selection")

service = st.sidebar.radio("Kaunsi file banani hai?", ["TP Filing", "CTM Filing"], key="service_choice")

uploaded_file = st.file_uploader(f"Upload Excel for {service}", type="xlsx", key=f"up_{service}")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        
        col1, col2 = st.columns(2)
        with col1:
            sheet = st.selectbox("Sheet Select Karein:", xl.sheet_names, key=f"sh_{service}")
        with col2:
            # Automatic index hata diya, ab aap manually daal sakte ho
            h_row = st.number_input("Header Row Index (0 se shuru karein):", min_value=0, value=2, key=f"hr_{service}")

        df = pd.read_excel(uploaded_file, sheet_name=sheet, header=h_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')

        json_files = {}

        # ---------------------------------------------------------
        # SERVICE 1: TP FILING (Grouping by JOB NO.)
        # ---------------------------------------------------------
        if service == "TP Filing":
            job_col = 'JOB NO.' if 'JOB NO.' in df.columns else 'JOB NO. '
            if job_col in df.columns:
                df[job_col] = df[job_col].ffill()
                for job_id, group in df.groupby(job_col):
                    first_row = group.iloc[0]
                    clean_id = str(job_id).replace("SINGLE ", "").replace(" ", "").replace(".0", "")
                    
                    template = {
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
                        template["atsStep2"]["lineDetails"].append({
                            "cargo_Transfer_Manifestno": clean_val(row.get('CTM NO')),
                            "cargo_Transfer_Manifestdate": format_date(row.get('CTM DATE')),
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "consignment_Value_INR": clean_val(row.get('VALUE', 0))
                        })
                        template["atsStep2"]["truckDetails"].append({
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "truck_Number": "", "seal_Number": "",
                            "flight_Number": str(row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(row.get('FLIGHT DATE'))
                        })
                    json_files[f"{clean_id}_TP.json"] = json.dumps(template, indent=2)

        # ---------------------------------------------------------
        # SERVICE 2: CTM FILING (Grouping by IGM)
        # ---------------------------------------------------------
        elif service == "CTM Filing":
            if 'IGM' in df.columns:
                df['IGM'] = df['IGM'].ffill()
                for igm_id, group in df.groupby('IGM'):
                    first_row = group.iloc[0]
                    clean_igm = clean_val(igm_id)
                    
                    template = {
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
                        template["freshCTMStep2"]["line_details"].append({
                            "customsHouseCode": clean_val(row.get('BOND PORT', 'INCCU4')),
                            "masterAirwayBillNumber": mawb, "houseAirwayBillNumber": ""
                        })
                    json_files[f"IGM_{clean_igm}_CTM.json"] = json.dumps(template, indent=2)

        # --- Download ---
        if json_files:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f_name, content in json_files.items():
                    zip_file.writestr(f_name, content)
            
            st.divider()
            st.success(f"{len(json_files)} Files taiyaar hain!")
            st.download_button(
                label=f"📥 DOWNLOAD {service.upper()} ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"{service.replace(' ', '_')}_Export.zip",
                mime="application/zip",
                key=f"final_btn_{service}"
            )
        else:
            st.error("Kuch gadbad hai! 'JOB NO.' ya 'IGM' column nahi mila. Header Index check karein.")

    except Exception as e:
        st.error(f"Error: {e}")