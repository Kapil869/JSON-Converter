import streamlit as st
import pandas as pd
import json
from datetime import datetime
import io
import zipfile

st.set_page_config(page_title="Logistics JSON Suite", layout="wide")

# --- Common Utilities ---
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
    try:
        return str(int(float(val)))
    except:
        return str(val).strip()

# --- Main Interface ---
st.title("📦 Logistics JSON Converter")
st.markdown("Choose your service and upload the Excel file.")

# Sidebar or Radio to separate the two tools completely
service = st.sidebar.selectbox("Select Service Type", ["TP Filing", "CTM Filing"])

uploaded_file = st.file_uploader(f"Upload Excel for {service}", type="xlsx")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        sheet = st.selectbox("Select Sheet:", xl.sheet_names)
        h_row = st.number_input("Header Row Index:", min_value=0, value=2)

        df = pd.read_excel(uploaded_file, sheet_name=sheet, header=h_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')

        if 'JOB NO.' in df.columns:
            df['JOB NO.'] = df['JOB NO.'].ffill()
            unique_jobs = df['JOB NO.'].unique()
            json_files = {}

            # ---------------------------------------------------------
            # LOGIC 1: TP FILING
            # ---------------------------------------------------------
            if service == "TP Filing":
                for job_id in unique_jobs:
                    group = df[df['JOB NO.'] == job_id]
                    first_row = group.iloc[0]
                    clean_id = str(job_id).replace("SINGLE ", "").replace(" ", "")

                    tp_template = {
                        "webFormId": "",
                        "webFormTypeId": "24",
                        "icegateId": "INDIGOCARGO",
                        "thumbPrint": "15 58 d8 6a 4e 61 5a e3 32 2c 5c 78 4a 3e d4 4e 09 0e 6a 76",
                        "serialNumber": "0a 8e 97 45 d6 5d",
                        "roleId": 7,
                        "url": "igm-egm/air-atp",
                        "atsStep1": {
                            "message_type": "F",
                            "unique_job_id": clean_id,
                            "custom_house_code": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "port_destination": "INMAA4",
                            "transhipment_Agency_Type": "DA", 
                            "transhipment_Agency_Code": "6E",
                            "gateway_Custodian_Code": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_Transport": "A",
                            "airline_Code": "6E",
                            "carrier_Code": "AABCI2726B",
                            "flight_Number": str(first_row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(first_row.get('FLIGHT DATE')),
                            "bond_Port": clean_val(first_row.get('BOND PORT', 'INCCU4'))
                        },
                        "atsStep2": {
                            "lineDetails": [],
                            "truckDetails": []
                        }
                    }

                    for _, row in group.iterrows():
                        mawb = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "").replace(".0", "")
                        tp_template["atsStep2"]["lineDetails"].append({
                            "cargo_Transfer_Manifestno": clean_val(row.get('CTM NO')),
                            "cargo_Transfer_Manifestdate": format_date(row.get('CTM DATE')),
                            "masterAirway_Bill_Number": mawb,
                            "houseAirway_Bill_Number": "",
                            "consignment_Value_INR": clean_val(row.get('VALUE', 0))
                        })
                        tp_template["atsStep2"]["truckDetails"].append({
                            "masterAirway_Bill_Number": mawb,
                            "houseAirway_Bill_Number": "",
                            "truck_Number": "",
                            "seal_Number": "",
                            "flight_Number": str(row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(row.get('FLIGHT DATE'))
                        })
                    json_files[f"{clean_id}_TP.json"] = json.dumps(tp_template, indent=2)

            # ---------------------------------------------------------
            # LOGIC 2: CTM FILING
            # ---------------------------------------------------------
            elif service == "CTM Filing":
                for job_id in unique_jobs:
                    group = df[df['JOB NO.'] == job_id]
                    first_row = group.iloc[0]
                    clean_id = str(job_id).replace("SINGLE ", "").replace(" ", "")

                    ctm_template = {
                        "webFormId": "",
                        "webFormTypeId": "21",
                        "icegateId": "INDIGOCARGO",
                        "roleId": 7,
                        "url": "igm-egm/ctm-webform",
                        "freshCTMStep1": {
                            "messageType": "F",
                            "customsHouseCode": clean_val(first_row.get('BOND PORT', 'INCCU4')),
                            "fileName": clean_id,
                            "iGMNumber": clean_val(first_row.get('IGM NO', '')),
                            "AirlineCode": "6E",
                            "iGMDate": format_date(first_row.get('IGM DATE')),
                            "portofDestination": "INMAA4",
                            "GatewayCustodianCode": clean_val(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_of_transport": "ACC"
                        },
                        "freshCTMStep2": {
                            "line_details": []
                        }
                    }

                    for _, row in group.iterrows():
                        mawb = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "").replace(".0", "")
                        ctm_template["freshCTMStep2"]["line_details"].append({
                            "customsHouseCode": clean_val(row.get('BOND PORT', 'INCCU4')),
                            "masterAirwayBillNumber": mawb,
                            "houseAirwayBillNumber": ""
                        })
                    json_files[f"{clean_id}_CTM.json"] = json.dumps(ctm_template, indent=2)

            # --- Final ZIP Download ---
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f_name, content in json_files.items():
                    zip_file.writestr(f_name, content)
            
            st.divider()
            st.success(f"Successfully processed {len(unique_jobs)} files for {service}.")
            st.download_button(
                label=f"📥 DOWNLOAD ALL {service} FILES (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"{service.replace(' ', '_')}_Export.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"Something went wrong: {e}")