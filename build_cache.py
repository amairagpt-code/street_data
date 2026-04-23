import re                                                                                                                                                        
import pandas as pd                                                                                                                                              
import numpy as np
import s3fs
                                       
STATE_CODES = {                  
    1:'Alabama',2:'Alaska',4:'Arizona',5:'Arkansas',6:'California',    
    8:'Colorado',9:'Connecticut',10:'Delaware',11:'District of Columbia',
    12:'Florida',13:'Georgia',15:'Hawaii',16:'Idaho',17:'Illinois',            
    18:'Indiana',19:'Iowa',20:'Kansas',21:'Kentucky',22:'Louisiana',            
    23:'Maine',24:'Maryland',25:'Massachusetts',26:'Michigan',
    27:'Minnesota',28:'Mississippi',29:'Missouri',30:'Montana',                                                                                                  
    31:'Nebraska',32:'Nevada',33:'New Hampshire',34:'New Jersey',                                                                                                
    35:'New Mexico',36:'New York',37:'North Carolina',38:'North Dakota',        
    39:'Ohio',40:'Oklahoma',41:'Oregon',42:'Pennsylvania',                      
    44:'Rhode Island',45:'South Carolina',46:'South Dakota',47:'Tennessee',    
    48:'Texas',49:'Utah',50:'Vermont',51:'Virginia',53:'Washington',
    54:'West Virginia',55:'Wisconsin',56:'Wyoming'
}                                                                              
                                                                               
def assign_color(row):
    if row["DRUNK_DR"] > 0:   return "#ff4444"                                  
    elif row["PBICYC"] > 0:   return "#00d4ff"
    elif row["PEDS"] > 0:     return "#ffd700"                                                                                                                  
    else:                      return "#ff8c00"                                
                                                                               
S3_BASE_PATH = "farsincidents/tempdata/"  
fs = s3fs.S3FileSystem()                                                                                                                        
k = 6378137

ACC_COLS = ['ST_CASE','YEAR','STATE','MONTH','DAY','HOUR','LATITUDE','LONGITUD','FATALS','PEDS']
accident_files = list({f.lower(): f for f in (
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Aa][Cc][Cc][Ii][Dd][Ee][Nn][Tt].csv") +
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Aa][Cc][Cc][Ii][Dd][Ee][Nn][Tt].CSV")
)}.values())
dfs = []
for f in accident_files:
    print("Reading accident:", f)
    temp = pd.read_csv(f"s3://{f}", encoding="latin1", low_memory=False)
    temp.columns = temp.columns.str.upper()
    dfs.append(temp[[c for c in ACC_COLS if c in temp.columns]])
df = pd.concat(dfs, ignore_index=True)
vehicle_files = list({f.lower(): f for f in (
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Vv][Ee][Hh][Ii][Cc][Ll][Ee].csv") +
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Vv][Ee][Hh][Ii][Cc][Ll][Ee].CSV")
)}.values())
vdfs = []
for f in vehicle_files:
    match = re.search(r"FARS(\d{4})NationalCSV", f, re.IGNORECASE)
    year = int(match.group(1)) if match else None
    temp = pd.read_csv(f"s3://{f}", encoding="latin1", low_memory=False,
                       usecols=lambda c: c in ['ST_CASE','DR_DRINK'])
    temp["YEAR"] = year
    vdfs.append(temp)
veh = pd.concat(vdfs, ignore_index=True)
drunk_counts = veh[veh["DR_DRINK"]==1].groupby(["YEAR","ST_CASE"]).size().reset_index(name="DRUNK_DR")
del veh
df = pd.merge(df, drunk_counts, on=["YEAR","ST_CASE"], how="left")
df["DRUNK_DR"] = df["DRUNK_DR"].fillna(0).astype(int)
del drunk_counts
person_files = list({f.lower(): f for f in (                                                                                                    
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Pp][Ee][Rr][Ss][Oo][Nn].csv") +
    fs.glob(S3_BASE_PATH + "FARS*NationalCSV/*[Pp][Ee][Rr][Ss][Oo][Nn].CSV")
)}.values())
pdfs = []
for f in person_files:
    match = re.search(r"FARS(\d{4})NationalCSV", f, re.IGNORECASE)
    year = int(match.group(1)) if match else None
    print("Reading person:", f)
    temp = pd.read_csv(f"s3://{f}", encoding="latin1", low_memory=False,
                       usecols=lambda c: c in ['ST_CASE','PER_TYP','AGE'])
    temp["YEAR"] = year
    pdfs.append(temp)
per = pd.concat(pdfs, ignore_index=True)

# cyclists
cyclist_counts = per[per["PER_TYP"]==6].groupby(["YEAR","ST_CASE"]).size().reset_index(name="PBICYC")
df = pd.merge(df, cyclist_counts, on=["YEAR","ST_CASE"], how="left")
df["PBICYC"] = df["PBICYC"].fillna(0).astype(int)

# age groups -- flag if ANY person in crash belongs to each group
# unknown/invalid ages are 998, 999 -- exclude
per_age = per[per["AGE"] < 998].copy()

for col, lo, hi in [
    ("HAS_CHILD",  0,  15),
    ("HAS_YOUTH",  16, 20),
    ("HAS_ADULT",  21, 59),
    ("HAS_OLDER",  60, 120),
]:
    grp = per_age[(per_age["AGE"] >= lo) & (per_age["AGE"] <= hi)]
    flags = grp.groupby(["YEAR","ST_CASE"]).size().reset_index(name=col)
    flags[col] = 1
    df = pd.merge(df, flags, on=["YEAR","ST_CASE"], how="left")
df[col] = df[col].fillna(0).astype(int)

del per

# coordinates
df = df[
    (df["LATITUDE"].notna()) & (df["LONGITUD"].notna()) &
    (df["LATITUDE"] != 0)    & (df["LONGITUD"] != 0)
]
continental = ((df["LONGITUD"]>=-130)&(df["LONGITUD"]<=-65)&(df["LATITUDE"]>=23)&(df["LATITUDE"]<=50))
alaska      = ((df["LONGITUD"]>=-180)&(df["LONGITUD"]<=-129)&(df["LATITUDE"]>=50)&(df["LATITUDE"]<=73))
hawaii      = ((df["LONGITUD"]>=-162)&(df["LONGITUD"]<=-153)&(df["LATITUDE"]>=17)&(df["LATITUDE"]<=23))
df = df[continental|alaska|hawaii]

df["x"] = df["LONGITUD"] * (k * 3.141592653589793 / 180)
df["y"] = np.log(np.tan((90 + df["LATITUDE"]) * 3.141592653589793 / 360)) * k
df["STATE_NAME"] = df["STATE"].map(STATE_CODES).fillna("Unknown")
df["YEAR_STR"]   = df["YEAR"].astype(str)
df["color"]      = df.apply(assign_color, axis=1)
df["HOUR_STR"]   = df["HOUR"].apply(lambda h: f"{int(h):02d}:00" if pd.notna(h) and 0<=h<=23 else "Unknown")
if "PEDS" not in df.columns: df["PEDS"] = 0
df["PEDS"] = pd.to_numeric(df["PEDS"], errors="coerce").fillna(0).astype(int)

print("Final rows:", len(df))
print("Columns:", df.columns.tolist())
df.to_parquet("/home/ubuntu/fars_cache.parquet", index=False)
print("Cache saved!") 

