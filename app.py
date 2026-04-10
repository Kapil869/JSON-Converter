import streamlit as st
import pandas as pd
import json
import io
import zipfile
from datetime import datetime

st.set_page_config(page_title="Logistics JSON", layout="wide")

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

def clean_flight(val):
    if pd.isna(val): 
        return ""
    s = str(val).strip()
    if s.lower() == "inf":
        return ""
    s = s.replace("+", "").replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def format_mawb(val):
    return str(val).replace("-", "").replace(" ", "").replace(".0", "")

def format_destination(val):
    dest = str(val).strip().upper()
    if not dest: return ""
    if not dest.startswith("IN"): dest = "IN" + dest
    if not dest.endswith("4"): dest = dest + "4"
    return dest

# --- UI Layout ---
st.title("📦 JSON Converter CTM TP ")

service = st.selectbox("What do you want to process?", ["TP Filing", "CTM Filing"], key="main_service")
uploaded_file = st.file_uploader(f"Upload Excel File", type="xlsx")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        sheet_names = xl.sheet_names
        
        selected_sheet = ""
        header_idx = 2 
        
        if service == "TP Filing":
            matches = [s for s in sheet_names if 'TP' in s.upper()]
            selected_sheet = matches[0] if matches else sheet_names[0]
            header_idx = 2
        else:
            matches = [s for s in sheet_names if 'CTM' in s.upper()]
            selected_sheet = matches[0] if matches else sheet_names[0]
            header_idx = 3

        st.info(f"Automatically selected sheet: **{selected_sheet}**")
        
        # dtype=str prevents scientific notation/inf issues shuru se hi
        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=header_idx, dtype=str)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')

        json_files = {}

        # ---------------------------------------------------------
        # TP FILING LOGIC
        # ---------------------------------------------------------
        if service == "TP Filing":
            job_col = 'JOB NO.' if 'JOB NO.' in df.columns else 'JOB NO. '
            if job_col in df.columns:
                df[job_col] = df[job_col].ffill()
                # sort=False ensures files follow the Excel sequence
                for job_id, group in df.groupby(job_col, sort=False):
                    first_row = group.iloc[0]
                    clean_id = str(job_id).replace("SINGLE ", "").replace(" ", "").replace(".0", "")
                    
                    tp_template = {
                        "webFormId": "", "webFormTypeId": "24", "icegateId": "INDIGOCARGO",
                        "thumbPrint": "15 58 d8 6a 4e 61 5a e3 32 2c 5c 78 4a 3e d4 4e 09 0e 6a 76",
                        "serialNumber": "0a 8e 97 45 d6 5d", "roleId": 7, "url": "igm-egm/air-atp",
                        "atsStep1": {
                            "message_type": "F", "unique_job_id": clean_id,
                            "custom_house_code": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "port_destination": format_destination(first_row.get('DEST', '')), 
                            "transhipment_Agency_Type": "DA", 
                            "transhipment_Agency_Code": "6E", 
                            "gateway_Custodian_Code": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_Transport": "A", "airline_Code": "6E", "carrier_Code": "AABCI2726B",
                            "flight_Number": clean_flight(first_row.get('BY AIR FLIGHT NO', '')),
                            "flight_Date": format_date(first_row.get('FLIGHT DATE')), "bond_Port": clean_val(first_row.get('BOND PORT', 'INCCU4'))
                        },
                        "atsStep2": { "lineDetails": [], "truckDetails": [] }
                    }
                    for _, row in group.iterrows():
                        mawb = format_mawb(row.get('MAWB NO', ''))
                        tp_template["atsStep2"]["lineDetails"].append({
                            "cargo_Transfer_Manifestno": clean_val(row.get('CTM NO')),
                            "cargo_Transfer_Manifestdate": format_date(row.get('CTM DATE')),
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "consignment_Value_INR": clean_val(row.get('VALUE', 0))
                        })
                        tp_template["atsStep2"]["truckDetails"].append({
                            "masterAirway_Bill_Number": mawb, "houseAirway_Bill_Number": "",
                            "truck_Number": "", "seal_Number": "",
                            "flight_Number": clean_flight(row.get('BY AIR FLIGHT NO', '')),
                            "flight_Date": format_date(row.get('FLIGHT DATE'))
                        })
                    json_files[f"{clean_id}_TP.json"] = json.dumps(tp_template, indent=2)

        # ---------------------------------------------------------
        # CTM FILING LOGIC
        # ---------------------------------------------------------
        elif service == "CTM Filing":
            group_cols = ['MAWB NO', 'IGM']
            if all(col in df.columns for col in group_cols):
                df['IGM'] = df['IGM'].ffill()
                ctm_counter = 1
                
                # sort=False stops alphabetical sorting, keeps Excel order
                for (mawb_val, igm_val), group in df.groupby(group_cols, sort=False):
                    first_row = group.iloc[0]
                    dest_formatted = format_destination(first_row.get('DESTINATION', ''))
                    mawb_clean = format_mawb(mawb_val)
                    
                    file_name_label = f"CTM{ctm_counter}"
                    
                    ctm_template = {
                        "webFormId": "", "webFormTypeId": "21", "icegateId": "INDIGOCARGO",
                        "thumbPrint": "15 58 d8 6a 4e 61 5a e3 32 2c 5c 78 4a 3e d4 4e 09 0e 6a 76",
                        "serialNumber": "0a 8e 97 45 d6 5d",
                        "roleId": 7, "url": "igm-egm/ctm-webform",
                        "freshCTMStep1": {
                            "messageType": "F", 
                            "customsHouseCode": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "fileName": file_name_label, 
                            "iGMNumber": clean_val(igm_val),
                            "AirlineCode": "6E", 
                            "iGMDate": format_date(first_row.get('IGM DATE')),
                            "portofDestination": dest_formatted, 
                            "GatewayCustodianCode": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_of_transport": "ACC"
                        },
                        "freshCTMStep2": { 
                            "line_details": [
                                {
                                    "customsHouseCode": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                                    "masterAirwayBillNumber": mawb_clean, 
                                    "houseAirwayBillNumber": ""
                                }
                            ]
                        }
                    }
                    json_files[f"{file_name_label}.json"] = json.dumps(ctm_template, indent=2)
                    ctm_counter += 1

        if json_files:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f_name, content in json_files.items():
                    zip_file.writestr(f_name, content)
            
            st.divider()
            st.success(f"Generated {len(json_files)} files in correct order.")
            st.download_button(
                label=f"📥 DOWNLOAD {service.upper()} ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"{service.replace(' ', '_')}.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"Error: {e}")