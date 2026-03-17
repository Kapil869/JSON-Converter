import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="Excel to JSON Pro", layout="wide")

def format_date(date_val):
    """Converts any date format to exact ISO string required."""
    try:
        if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).lower() == "nat":
            return ""
        # Convert to datetime object
        dt = pd.to_datetime(date_val, dayfirst=True)
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')
    except:
        return ""

def clean_number_string(val):
    """Strictly removes .0 and ensures the value is a clean string."""
    if pd.isna(val):
        return ""
    
    # Convert to string first
    s = str(val).strip()
    
    # If it ends with .0, remove it
    if s.endswith('.0'):
        s = s[:-2]
        
    return s

st.title("📦JSON Converter")


uploaded_file = st.file_uploader("Upload XLSX File", type="xlsx")

if uploaded_file:
    try:
        xl = pd.ExcelFile(uploaded_file)
        
        col1, col2 = st.columns(2)
        with col1:
            selected_sheet = st.selectbox("Select Sheet:", xl.sheet_names)
        with col2:
            header_row = st.number_input("Header Row (Usually 2 for your file):", min_value=0, value=2)

        if st.button("Generate Final JSON"):
            df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=header_row)
            df.columns = df.columns.str.strip()
            df = df.dropna(how='all')
            
            if 'JOB NO.' in df.columns:
                df['JOB NO.'] = df['JOB NO.'].ffill()
                output_list = []
                
                for job_id, group in df.groupby('JOB NO.'):
                    first_row = group.iloc[0]
                    
                    # Create the specific template structure
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
                            "unique_job_id": clean_number_string(job_id).replace("SINGLE ", ""),
                            "custom_house_code": clean_number_string(first_row.get('BOND PORT', 'INCCU4')),
                            "port_destination": "INMAA4",
                            "transhipment_Agency_Type": clean_number_string(first_row.get('AGENCY CODE', 'DA')),
                            "transhipment_Agency_Code": "6E",
                            "gateway_Custodian_Code": clean_number_string(first_row.get('CUSTODIAN CODE', 'INCCU4AAI1')),
                            "mode_Transport": "A",
                            "airline_Code": "6E",
                            "carrier_Code": "AABCI2726B",
                            "flight_Number": str(first_row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(first_row.get('FLIGHT DATE')),
                            "bond_Port": clean_number_string(first_row.get('BOND PORT', 'INCCU4'))
                        },
                        "atsStep2": {
                            "lineDetails": [],
                            "truckDetails": []
                        }
                    }

                    for _, row in group.iterrows():
                        # Clean MAWB: remove dashes, spaces, and trailing .0
                        mawb_raw = str(row.get('MAWB NO', '')).replace("-", "").replace(" ", "")
                        if mawb_raw.endswith('.0'): mawb_raw = mawb_raw[:-2]
                        
                        # Add to lineDetails
                        template["atsStep2"]["lineDetails"].append({
                            "cargo_Transfer_Manifestno": clean_number_string(row.get('CTM NO')),
                            "cargo_Transfer_Manifest_Date": format_date(row.get('CTM DATE')),
                            "masterAirway_Bill_Number": mawb_raw,
                            "houseAirway_Bill_Number": "",
                            "origin_Port": clean_number_string(row.get('ORIGIN')),
                            "destination_Port": clean_number_string(row.get('DEST')),
                            "quantity_Number_of_Packages": 0,
                            "weight_Gross_Weight": 0.0,
                            "value_of_Cargo": float(row.get('VALUE', 0))
                        })
                        
                        # Add to truckDetails
                        template["atsStep2"]["truckDetails"].append({
                            "masterAirway_Bill_Number": mawb_raw,
                            "houseAirway_Bill_Number": "",
                            "truck_Number": "",
                            "seal_Number": "",
                            "flight_Number": str(row.get('BY AIR FLIGHT NO', '')).replace(" ", "").replace(".0", ""),
                            "flight_Date": format_date(row.get('FLIGHT DATE'))
                        })

                    output_list.append(template)

                # Return single object if only 1 job, else list
                final_data = output_list[0] if len(output_list) == 1 else output_list
                json_result = json.dumps(final_data, indent=2)

                st.success("JSON Generated Successfully!")
                st.download_button("Download JSON", json_result, "data.json", "application/json")
                st.json(json_result)
            else:
                st.error("Could not find 'JOB NO.' column. Try changing the Header Row Index.")

    except Exception as e:
        st.error(f"Processing Error: {e}")