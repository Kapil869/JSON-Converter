import streamlit as st
import pandas as pd
import json
from datetime import datetime
import io
import zipfile

st.set_page_config(page_title="TP JSON Bulk Exporter", layout="wide")

def format_date(date_val):
    try:
        if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).lower() == "nat":
            return ""
        dt = pd.to_datetime(date_val, dayfirst=True)
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')
    except:
        return ""

def clean_to_int_string(val):
    if pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        return str(int(float(val)))
    except:
        return str(val).strip()

st.title("📦 Logistics ZIP Generator")


uploaded_file = st.file_uploader("Upload Excel (.xlsx) File", type="xlsx")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        col1, col2 = st.columns(2)
        with col1:
            selected_sheet = st.selectbox("Select Sheet:", xl.sheet_names)
        with col2:
            header_row = st.number_input("Header Row Index:", min_value=0, value=2)

        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=header_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')

        if 'JOB NO.' in df.columns:
            df['JOB NO.'] = df['JOB NO.'].ffill()
            unique_jobs = df['JOB NO.'].unique()
            
            json_files = {}

            for job_id in unique_jobs:
                group = df[df['JOB NO.'] == job_id]
                first_row = group.iloc[0]
                
                clean_job_name = str(job_id).replace("SINGLE ", "").replace(" ", "")

                template = {
                    "webFormId": "",
                    "webFormTypeId": "24",
                    "icegateId": "INDIGOCARGO",
                    "thumbPrint": "15 58 d8 6a 4e 61 5a e3 32 2c 5c 78 4a 3e d4 4e 09 0e 6a 76",
                    "serialNumber": "0a 8e 97 45 d6 5d",
                    "roleId": 7,
                    "url": "igm-egm/air-atp",
                    "atsStep1": {
                        "message_type": "F",
                        "unique_job_id": clean_job_name,
                        "custom_house_code": clean_to_int_string(first_row.get('BOND PORT', 'INCCU4')),
                        "port_destination": "INMAA4",
                        "transhipment_Agency_Type": "DA", 
                        "transhipment_Agency_Code": "6E",
                        "gateway_Custodian_Code": clean_to_int_string(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                        "mode_Transport": "A",
                        "airline_Code": "6E",
                        "carrier_Code": "AABCI2726B",
                        "flight_Number": str(first_row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                        "flight_Date": format_date(first_row.get('FLIGHT DATE')),
                        "bond_Port": clean_to_int_string(first_row.get('BOND PORT', 'INCCU4'))
                    },
                    "atsStep2": {
                        "lineDetails": [],
                        "truckDetails": []
                    }
                }

                for _, row in group.iterrows():
                    mawb = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "").replace(".0", "")
                    
                    # Line Details (Required fields only)
                    template["atsStep2"]["lineDetails"].append({
                        "cargo_Transfer_Manifestno": clean_to_int_string(row.get('CTM NO')),
                        "cargo_Transfer_Manifest_Date": format_date(row.get('CTM DATE')),
                        "masterAirway_Bill_Number": mawb,
                        "value_of_Cargo": float(row.get('VALUE', 0))
                    })
                    
                    # Truck Details (Including truck_Number and seal_Number)
                    template["atsStep2"]["truckDetails"].append({
                        "masterAirway_Bill_Number": mawb,
                        "truck_Number": "",
                        "seal_Number": "",
                        "flight_Number": str(row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                        "flight_Date": format_date(row.get('FLIGHT DATE'))
                    })

                json_files[f"{clean_job_name}.json"] = json.dumps(template, indent=2)

            # Create ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_name, content in json_files.items():
                    zip_file.writestr(file_name, content)
            
            st.divider()
            st.success(f"Successfully processed {len(unique_jobs)} Job(s).")
            
            # Single Download Button
            st.download_button(
                label="📥 DOWNLOAD ALL JSON FILES AS ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"TP_JSON_Files_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"Processing Error: {e}")