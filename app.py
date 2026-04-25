import re
import math
import requests
import pandas as pd
import numpy as np
from bokeh.plotting import figure, curdoc
from bokeh.models import (
    ColumnDataSource, HoverTool, Select, WMTSTileSource,
    RangeSlider, TextInput, Button, Tabs, TabPanel, TapTool, CustomJS,
    FactorRange, Spacer
)
from bokeh.layouts import column, row
from bokeh.models.widgets import Div
from jinja2 import Template

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

STATE_POP = {
    'Alabama': 5024279, 'Alaska': 733391, 'Arizona': 7151502, 'Arkansas': 3011524,
    'California': 39538223, 'Colorado': 5773714, 'Connecticut': 3605944,
    'Delaware': 989948, 'District of Columbia': 689545, 'Florida': 21538187,
    'Georgia': 10711908, 'Hawaii': 1455271, 'Idaho': 1839106, 'Illinois': 12812508,
    'Indiana': 6785528, 'Iowa': 3190369, 'Kansas': 2937880, 'Kentucky': 4505836,
    'Louisiana': 4657757, 'Maine': 1362359, 'Maryland': 6177224,
    'Massachusetts': 7029917, 'Michigan': 10077331, 'Minnesota': 5706494,
    'Mississippi': 2961279, 'Missouri': 6154913, 'Montana': 1084225,
    'Nebraska': 1961504, 'Nevada': 3104614, 'New Hampshire': 1377529,
    'New Jersey': 9288994, 'New Mexico': 2117522, 'New York': 20201249,
    'North Carolina': 10439388, 'North Dakota': 779094, 'Ohio': 11799448,
    'Oklahoma': 3959353, 'Oregon': 4237256, 'Pennsylvania': 13002700,
    'Rhode Island': 1097379, 'South Carolina': 5118425, 'South Dakota': 886667,
    'Tennessee': 6910840, 'Texas': 29145505, 'Utah': 3271616, 'Vermont': 643077,
    'Virginia': 8631393, 'Washington': 7705281, 'West Virginia': 1793716,
    'Wisconsin': 5893718, 'Wyoming': 576851
}

def assign_color(row):
    if row["DRUNK_DR"] > 0:
        return "#ff4444"
    elif row["PBICYC"] > 0:
        return "#00d4ff"
    elif row["PEDS"] > 0:
        return "#ffd700"
    else:
        return "#ff8c00"

df = pd.read_parquet("/home/ubuntu/fars_cache.parquet")
print("Loaded", len(df), "rows from cache")

k = 6378137

print("Building year index...")
df_by_year = {yr: grp.reset_index(drop=True) for yr, grp in df.groupby("YEAR")}
print("Year index built for years:", sorted(df_by_year.keys()))

states = ["All"] + sorted(df["STATE_NAME"].unique().tolist())
years  = sorted(df["YEAR_STR"].unique().tolist(), reverse=True)
most_recent_year = years[0] if years else "2023"
second_year      = years[1] if len(years) > 1 else years[0]

all_years  = sorted(df["YEAR"].unique().tolist())
min_year   = all_years[0]
max_year   = all_years[-1]
_min_year  = min_year
_max_year  = max_year

bucket_start = (min_year // 5) * 5
years_5yr = []
y = bucket_start
while y <= max_year:
    y_end = min(y + 4, max_year)
    if y_end >= min_year:
        years_5yr.append(f"{max(y, min_year)}-{y_end}")
    y += 5

default_5yr = years_5yr[-1] if years_5yr else f"{min_year}-{max_year}"

# map bounds: centered on continental US
USA_X_MIN, USA_X_MAX = -14471534, -7235767
USA_Y_MIN, USA_Y_MAX =  2632019,   6446276

DOT_LIMIT = 50000

TILE_URL    = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
DARK_BG     = "#0d0d1a"
DARK_PANEL  = "#1a1a2e"
DARK_BORDER = "#2a2a4a"
TEXT_DIM    = "#666666"
TEXT_LIGHT  = "#e0e0e0"

def style(widget, width=200):
    widget.width = width
    widget.stylesheets = [f"""
        :host .bk-input {{
            background: {DARK_PANEL};
            color: {TEXT_LIGHT};
            border: 1px solid {DARK_BORDER};
            border-radius: 20px;
            padding: 5px 12px;
            font-size: 12px;
        }}
        :host .bk-input:hover {{ border-color: #555; }}
        :host label {{
            color: {TEXT_DIM};
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
    """]
    return widget

def divider(width=200):
    return Div(width=width, text='<div style="border-top:1px solid #1e1e3a;margin:8px 0;"></div>')

def make_map(title_text):
    p = figure(
        x_axis_type="mercator", y_axis_type="mercator",
        x_range=(USA_X_MIN, USA_X_MAX), y_range=(USA_Y_MIN, USA_Y_MAX),
        sizing_mode="stretch_both",
        tools="pan,wheel_zoom,box_zoom,reset", active_scroll="wheel_zoom"
    )
    p.add_tile(WMTSTileSource(url=TILE_URL))
    p.axis.visible = False
    p.grid.visible = False
    p.background_fill_color = "#1a1a1a"
    p.border_fill_color     = "#1a1a1a"
    p.outline_line_color    = None
    p.title.text            = title_text
    p.title.text_color      = TEXT_LIGHT
    p.title.text_font_size  = "13pt"
    p.title.align           = "center"
    return p

def make_source():
    return ColumnDataSource(data=dict(
        x=[], y=[], color=[],
        STATE_NAME=[], MONTH=[], DAY=[], YEAR=[], HOUR_STR=[],
        FATALS=[], DRUNK_DR=[], PEDS=[], PBICYC=[]
    ))

def add_hover(p, source, info_div):
    pts = p.scatter(
        x="x", y="y", size=5,
        fill_color="color", line_color=None,
        fill_alpha=0.75, source=source,
        nonselection_fill_alpha=0.3,
        selection_fill_color="white",
        selection_line_color="#4a90d9",
        selection_line_width=1
    )
    tap_cb = CustomJS(args=dict(source=source, div=info_div), code="""
        const idx = source.selected.indices;
        if (idx.length === 0) { div.text = ""; return; }

        const i = idx[0];
        const d = source.data;

        var involved = [];
        if (d.DRUNK_DR[i] > 0) involved.push("Drunk Driver");
        if (d.PEDS[i]    > 0) involved.push("Pedestrian");
        if (d.PBICYC[i]  > 0) involved.push("Cyclist");
        if (involved.length === 0) involved.push("None flagged");

        const x = d.x[i];
        const y = d.y[i];
        const k = 6378137;
        const lng = (x / k) * (180 / Math.PI);
        const lat = (2 * Math.atan(Math.exp(y / k)) - Math.PI / 2) * (180 / Math.PI);

        const apiKey = "AIzaSyAh1f2MC_LgXkyMOewvsEK21fdGiJL8jUY";
        const svThumb = "https://maps.googleapis.com/maps/api/streetview?size=400x220&location=" + lat + "," + lng + "&fov=80&heading=70&pitch=0&key=" + apiKey;

        function mkRow(label, value, color) {
            var c = color ? color : "#e0e0e0";
            return "<tr><td style='color:#555;font-size:10px;text-transform:uppercase;padding:3px 0;width:90px;'>" + label + "</td><td style='color:" + c + ";font-size:11px;font-weight:500;padding:3px 0;'>" + value + "</td></tr>";
        }

        window._sv_lat = lat;
        window._sv_lng = lng;
        window._sv_key = apiKey;

        window._sv_open = function() {
            var old = document.getElementById("sv-overlay");
            if (old) old.remove();

            var ov = document.createElement("div");
            ov.id = "sv-overlay";
            ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;";

            var panoDiv = document.createElement("div");
            panoDiv.id = "sv-pano";
            panoDiv.style.cssText = "width:90vw;height:80vh;border-radius:10px;overflow:hidden;";

            var btn = document.createElement("button");
            btn.textContent = "Close";
            btn.style.cssText = "margin-top:16px;background:#1a1a2e;color:#e0e0e0;border:1px solid #2a2a4a;border-radius:20px;padding:8px 28px;font-size:13px;cursor:pointer;";
            btn.onclick = function() { ov.remove(); };

            ov.appendChild(panoDiv);
            ov.appendChild(btn);
            document.body.appendChild(ov);

            function initPano() {
                var pano = new google.maps.StreetViewPanorama(panoDiv, {
                    position: { lat: window._sv_lat, lng: window._sv_lng },
                    pov: { heading: 70, pitch: 0 },
                    zoom: 1,
                    addressControl: false,
                    fullscreenControl: false
                });
            }

            if (typeof google !== "undefined" && google.maps) {
                initPano();
            } else {
                var script = document.createElement("script");
                script.src = "https://maps.googleapis.com/maps/api/js?key=" + window._sv_key + "&callback=_sv_initPano";
                window._sv_initPano = initPano;
                document.head.appendChild(script);
            }
        };

        var html = "<div style='font-family:sans-serif;padding:10px 0;'>";
        html += "<p style='color:#4a90d9;font-size:10px;text-transform:uppercase;font-weight:600;margin:0 0 8px;'>Crash Details</p>";
        html += "<table style='width:100%;border-collapse:collapse;'>";
        html += mkRow("State",      d.STATE_NAME[i]);
        html += mkRow("Date",       d.MONTH[i] + "/" + d.DAY[i] + "/" + d.YEAR[i]);
        html += mkRow("Time",       d.HOUR_STR[i]);
        html += mkRow("Fatalities", d.FATALS[i], "#ff4444");
        html += mkRow("Involved",   involved.join(", "), "#ffd700");
        html += "</table>";
        html += "<div style='margin-top:12px;'>";
        html += "<p style='color:#555;font-size:10px;text-transform:uppercase;margin:0 0 6px;'>Street View</p>";
        html += "<img src='" + svThumb + "' onclick='window._sv_open()' style='width:100%;border-radius:6px;border:1px solid #2a2a4a;display:block;cursor:pointer;' />";
        html += "<p style='color:#555;font-size:10px;margin:5px 0 0;text-align:center;'>Click image to explore Street View</p>";
        html += "</div></div>";

        div.text = html;
    """)
    source.selected.js_on_change("indices", tap_cb)
    p.add_tools(TapTool(renderers=[pts]))

def filter_df(year_str, state_val, drunk_val, ped_val, bike_val,
            h_min, h_max, age_val="All"):
    if "-" in str(year_str) and len(year_str) == 9:
        y1, y2 = int(year_str[:4]), int(year_str[5:])
        chunks = [df_by_year[yr] for yr in range(y1, y2 + 1) if yr in df_by_year]
        t = pd.concat(chunks, ignore_index=True) if chunks else df.iloc[0:0].copy()
    else:
        yr_int = int(year_str)
        t = df_by_year.get(yr_int, df.iloc[0:0]).copy()
    if state_val != "All":
        t = t[t["STATE_NAME"] == state_val]
    t = t[(t["HOUR"].notna()) & (t["HOUR"] >= h_min) & (t["HOUR"] <= h_max) & (t["HOUR"] < 99)]
    if drunk_val == "Drunk Drivers Involved":
        t = t[t["DRUNK_DR"] > 0]
    elif drunk_val == "No Drunk Drivers":
        t = t[t["DRUNK_DR"] == 0]
    if ped_val == "Pedestrian Involved":
        t = t[t["PEDS"] > 0]
    elif ped_val == "No Pedestrian":
        t = t[t["PEDS"] == 0]
    if bike_val == "Cyclist Involved":
        t = t[t["PBICYC"] > 0]
    elif bike_val == "No Cyclist":
        t = t[t["PBICYC"] == 0]
    if age_val == "Child (0-15)":
        t = t[t["HAS_CHILD"] > 0]
    elif age_val == "Youth (16-20)":
        t = t[t["HAS_YOUTH"] > 0]
    elif age_val == "Adult (21-59)":
        t = t[t["HAS_ADULT"] > 0]
    elif age_val == "Older Adult (60+)":
        t = t[t["HAS_OLDER"] > 0]
    return t

def to_source(t):
    if len(t) > DOT_LIMIT:
        t = t.sample(DOT_LIMIT, random_state=42)
    return {col: t[col].tolist() for col in
            ["x","y","color","STATE_NAME","MONTH","DAY","YEAR",
            "HOUR_STR","FATALS","DRUNK_DR","PEDS","PBICYC"]}

minimal_css = Div(sizing_mode="stretch_width", text="""
    <style>
    html, body, .bk-root { background: #0d0d1a !important; margin:0; padding:0; }
    .noUi-connect  { background: #555 !important; }
    .noUi-handle   { background: #e0e0e0 !important; border:none !important; border-radius:50% !important; box-shadow:none !important; }
    .noUi-base, .noUi-target { background: #2a2a4a !important; border:none !important; border-radius:4px !important; }
    .bk-tab        { background:#0d0d1a !important; color:#555 !important; border:none !important; border-bottom:2px solid transparent !important; border-radius:0 !important; padding:14px 32px !important; font-size:14px !important; font-weight:500 !important; letter-spacing:0.04em !important; text-transform:uppercase !important; }
    .bk-tab.bk-active { background:#0d0d1a !important; color:#e0e0e0 !important; border-bottom:2px solid #4a90d9 !important; }
    .bk-tab:hover  { color:#aaa !important; }
    .bk-tabs-header { background:#0d0d1a !important; border-bottom:1px solid #1e1e3a !important; padding:0 16px !important; }
    .bk-btn-default { background:transparent !important; border:1px solid #333 !important; color:#888 !important; border-radius:20px !important; font-size:12px !important; }
    .bk-btn-default:hover { border-color:#555 !important; color:#bbb !important; }
    .bk-btn-primary { background:#4a90d9 !important; border-color:#4a90d9 !important; color:#fff !important; border-radius:20px !important; font-size:13px !important; font-weight:600 !important; }
    .bk-btn-primary:hover { background:#5aa0e9 !important; }
    </style>
""")

legend_div = Div(width=200, text=f"""
<div style="border-top:1px solid #1e1e3a;padding-top:12px;margin-top:4px;font-family:sans-serif;">
    <p style="color:{TEXT_DIM};font-size:10px;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.05em;">Legend</p>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;"><span style="width:8px;height:8px;border-radius:50%;background:#ff4444;display:inline-block;"></span><span style="color:#aaa;font-size:11px;">Drunk driver</span></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;"><span style="width:8px;height:8px;border-radius:50%;background:#00d4ff;display:inline-block;"></span><span style="color:#aaa;font-size:11px;">Cyclist involved</span></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;"><span style="width:8px;height:8px;border-radius:50%;background:#ffd700;display:inline-block;"></span><span style="color:#aaa;font-size:11px;">Pedestrian involved</span></div>
    <div style="display:flex;align-items:center;gap:8px;"><span style="width:8px;height:8px;border-radius:50%;background:#ff8c00;display:inline-block;"></span><span style="color:#aaa;font-size:11px;">Other fatal crash</span></div>
</div>
""")

TOUR_STEPS = [
    ("Welcome to the FARS Crash Map",
     "This tool visualizes every fatal traffic crash in the US from 2001 to 2024, using data from the NHTSA Fatality Analysis Reporting System. Each dot on the map is one fatal crash.",
     "#4a90d9"),
    ("Year Filter",
     "Use the Year dropdown in the sidebar to select the range of years you would like to view and the map will update.",
     "#4a90d9"),
    ("State Filter",
     "Use the State dropdown to focus on a specific state, or keep it on All to see the entire country.",
     "#4a90d9"),
    ("Crash Type Filters",
     "Filter by who was involved. Red dots = drunk driver. Yellow = pedestrian. Cyan = cyclist. Orange = other fatal crash. Use the dropdowns to isolate any type.",
     "#ff8c00"),
    ("Age Group Filter",
     "Filter crashes by the age of any person involved. Choose Child (0-15), Youth (16-20), Adult (21-59), or Older Adult (60+).",
     "#c77dff"),
    ("Hour Range Slider",
     "Drag the slider handles to filter by time of day. For example, set it to 22-23 to see late-night crashes, or 7-9 for morning rush hour patterns.",
     "#f5c842"),
    ("Address Search",
     "Type any US address, city, or state and press Enter. The map zooms to that location automatically, all the way down to street level.",
     "#7bc67e"),
    ("Clicking a Dot",
     "Click any dot on the map to inspect that crash. A panel in the sidebar shows the location, date, time, fatalities, and who was involved.",
     "#7bc67e"),
    ("Year Comparison Tab",
     "The Year Comparison tab places two years side by side for the same state. Each side has independent filters, making year-over-year analysis easy.",
     "#4a90d9"),
    ("Charts Tab",
     "The Charts tab shows statistical breakdowns: crashes by hour, year trend, top states, and age group distribution. Use the filters to narrow the data.",
     "#4a90d9"),
    ("You Are All Set",
     "You now know how to use the FARS Crash Map. Use the filters to build a specific view, click dots to inspect crashes, and switch tabs to compare years or see charts. Click Return to Map to start exploring.",
     "#7bc67e"),
]

tour_step     = [0]
tour_tabs_ref = [None]

tour_card_div = Div(sizing_mode="stretch_width", text="")
tour_next_btn = Button(label="Next", button_type="primary", width=160)
tour_back_btn = Button(label="Back", button_type="default", width=130)
tour_exit_btn = Button(label="Return to Map", button_type="default", width=200)
tour_btn_row  = row(
    tour_exit_btn, tour_back_btn, tour_next_btn,
    sizing_mode="fixed", align="center",
    styles={"gap": "20px", "margin-top": "16px"}
)
tour_start_btn = Button(label="? Take a Tour", button_type="default", width=200)

def refresh_tour_card():
    i = tour_step[0]
    title, desc, color = TOUR_STEPS[i]
    n   = len(TOUR_STEPS)
    pct = int((i + 1) / n * 100)
    tour_card_div.text = (
        f'<div style="font-family:sans-serif;text-align:center;padding:48px 40px 24px;max-width:860px;margin:0 auto;">' 
        f'<p style="color:#555;font-size:13px;text-transform:uppercase;letter-spacing:0.12em;margin:0 0 16px;">Step {i+1} of {n}</p>'
        f'<h2 style="color:{color};font-size:clamp(26px,3.5vw,48px);font-weight:700;margin:0 0 20px;line-height:1.2;max-width:800px;">{title}</h2>'
        f'<p style="color:#ccc;font-size:clamp(15px,1.8vw,21px);line-height:1.8;margin:0 0 28px;max-width:720px;">{desc}</p>'
        f'<div style="background:#1e1e3a;border-radius:10px;height:6px;overflow:hidden;margin-bottom:10px;width:min(560px,80%);margin-left:auto;margin-right:auto;">' 
        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:10px;transition:width 0.3s;"></div></div>'
        f'<p style="color:#555;font-size:12px;margin:0;">{pct}% complete</p>'
        f'</div>'
    )
    tour_back_btn.visible = i > 0
    tour_next_btn.label   = "Finish" if i == n - 1 else "Next  >"

def tour_start_fn(n):
    tour_step[0] = 0
    refresh_tour_card()
    if tour_tabs_ref[0]:
        tour_tabs_ref[0].active = 3

def tour_next_fn(n):
    if tour_step[0] < len(TOUR_STEPS) - 1:
        tour_step[0] += 1
        refresh_tour_card()
    else:
        if tour_tabs_ref[0]:
            tour_tabs_ref[0].active = 0

def tour_back_fn(n):
    if tour_step[0] > 0:
        tour_step[0] -= 1
        refresh_tour_card()

def tour_exit_fn(n):
    if tour_tabs_ref[0]:
        tour_tabs_ref[0].active = 0

tour_start_btn.on_click(tour_start_fn)
tour_next_btn.on_click(tour_next_fn)
tour_back_btn.on_click(tour_back_fn)
tour_exit_btn.on_click(tour_exit_fn)

refresh_tour_card()

tour_layout = column(
    tour_card_div,
    row(Spacer(sizing_mode="stretch_width"), tour_btn_row, Spacer(sizing_mode="stretch_width")),
    sizing_mode="scale_width",
    styles={"background": "#0d0d1a", "padding-top": "0"}
)

W = 200

p1 = make_map("FARS Fatal Accident Visualization")
s1 = make_source()

info_div1 = Div(width=W, text='<p style="color:#333;font-size:11px;font-family:sans-serif;padding:8px 10px;margin:0;">Click any dot on the map</p>',
                styles={"background":"#111827","border-radius":"8px","border":"1px solid #1e1e3a","min-height":"300px"})
add_hover(p1, s1, info_div1)

address_input = style(TextInput(title="Search Location", placeholder="Search address or city..."))
sel_year1     = style(Select(title="Year Range", value=default_5yr, options=years_5yr))
sel_state1    = style(Select(title="State",  value="All", options=states))
sel_drunk1    = style(Select(title="Drunk Drivers", value="All", options=["All","Drunk Drivers Involved","No Drunk Drivers"]))
sel_ped1      = style(Select(title="Pedestrian", value="All", options=["All","Pedestrian Involved","No Pedestrian"]))
sel_bike1     = style(Select(title="Cyclist", value="All", options=["All","Cyclist Involved","No Cyclist"]))
sel_age1      = style(Select(title="Age Group", value="All", options=["All","Child (0-15)","Youth (16-20)","Adult (21-59)","Older Adult (60+)"]))
sel_norm1     = style(Select(title="View As", value="Raw Count", options=["Raw Count","Per 100k People"]))
hour_slider1  = style(RangeSlider(start=0, end=23, value=(0,23), step=1, title="Hour Range"))

stats_div = Div(width=W, text="", styles={
    "background": "#111827", "border-radius": "8px",
    "border": "1px solid #1e1e3a", "padding": "10px 12px",
    "margin-top": "6px", "font-family": "sans-serif"
})

crash_div = Div(width=W, text="", stylesheets=[f"""
    :host div {{ color:{TEXT_LIGHT}; font-size:13px; padding:6px 10px;
                 background:{DARK_PANEL}; border-radius:12px;
                 border:1px solid {DARK_BORDER}; margin-top:4px; }}
"""])

def update1(attr, old, new):
    t = filter_df(sel_year1.value, sel_state1.value, sel_drunk1.value,
                  sel_ped1.value, sel_bike1.value, *hour_slider1.value,
                  age_val=sel_age1.value)
    n      = len(t)
    fatals = int(t["FATALS"].sum())
    sampled = n > DOT_LIMIT
    if sel_norm1.value == "Per 100k People" and sel_state1.value != "All":
        crash_div.text = (f'<b style="color:#ff8c00">{n:,}</b> crashes (raw)')
    elif sel_norm1.value == "Per 100k People" and sel_state1.value == "All":
        crash_div.text = '<span style="color:#888;font-size:11px;">Select a state for per-100k view</span>'
    else:
        sample_note = f' <span style="color:#555;font-size:10px;">(showing {DOT_LIMIT:,})</span>' if sampled else ''
        crash_div.text = (f'<b style="color:#ff8c00">{n:,}</b> crashes &nbsp;|&nbsp; '
                          f'<b style="color:#ff4444">{fatals:,}</b> fatalities{sample_note}')
    month_names_s = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    if sel_state1.value != "All" and len(t) > 0:
        top_hour      = int(t[t["HOUR"] < 99]["HOUR"].value_counts().idxmax()) if (t["HOUR"] < 99).any() else 0
        top_month_num = int(t["MONTH"].value_counts().idxmax()) if len(t) > 0 else 0
        top_month     = month_names_s[top_month_num] if 1 <= top_month_num <= 12 else "N/A"
        pct_drunk     = round(len(t[t["DRUNK_DR"] > 0]) / len(t) * 100, 1)
        pct_ped       = round(len(t[t["PEDS"] > 0])    / len(t) * 100, 1)
        stats_div.text = (
            f'<p style="color:#555;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 8px;">State Summary</p>'
            f'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #1e1e3a;"><span style="color:#555;font-size:10px;">Deadliest Hour</span><span style="color:#e0e0e0;font-size:11px;font-weight:500;">{top_hour:02d}:00</span></div>'
            f'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #1e1e3a;"><span style="color:#555;font-size:10px;">Deadliest Month</span><span style="color:#e0e0e0;font-size:11px;font-weight:500;">{top_month}</span></div>'
            f'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #1e1e3a;"><span style="color:#555;font-size:10px;">Drunk Driver</span><span style="color:#ff4444;font-size:11px;font-weight:500;">{pct_drunk}%</span></div>'
            f'<div style="display:flex;justify-content:space-between;padding:3px 0;"><span style="color:#555;font-size:10px;">Pedestrian</span><span style="color:#ffd700;font-size:11px;font-weight:500;">{pct_ped}%</span></div>'
        )
        stats_div.visible = True
    else:
        stats_div.text    = ""
        stats_div.visible = False
    s1.data = to_source(t)

def search_address():
    addr = address_input.value.strip()
    if not addr: return
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": addr, "format": "json", "limit": 1},
            headers={"User-Agent": "FARS-Map/1.0"}, timeout=5
        ).json()
        if res:
            lat, lon  = float(res[0]["lat"]), float(res[0]["lon"])
            xc = lon * (k * math.pi / 180)
            yc = math.log(math.tan((90 + lat) * math.pi / 360)) * k
            osm_type  = res[0].get("type","")
            osm_class = res[0].get("class","")
            if osm_type == "state":                                                 delta = 350000
            elif osm_class == "boundary" and osm_type == "administrative":         delta = 25000
            elif osm_type in ("suburb","neighbourhood","quarter","village","town"): delta = 10000
            else:                                                                   delta = 1500
            p1.x_range.update(start=xc-delta, end=xc+delta)
            p1.y_range.update(start=yc-delta, end=yc+delta)
    except Exception as e:
        print(f"Search error: {e}")

address_input.on_change("value", lambda a, o, n: search_address())
for w in [sel_year1, sel_state1, sel_drunk1, sel_ped1, sel_bike1, sel_age1, sel_norm1]:
    w.on_change("value", update1)
hour_slider1.on_change("value_throttled", update1)

sidebar_title = Div(width=W, text=f"""
<div style="padding:4px 0 12px;border-bottom:1px solid #1e1e3a;font-family:sans-serif;">
    <p style="color:{TEXT_LIGHT};font-size:14px;font-weight:600;margin:0 0 2px;">FARS Fatal Crashes</p>
    <p style="color:{TEXT_DIM};font-size:11px;margin:0;">{_min_year} - {_max_year} · NHTSA</p>
</div>
""")

sidebar1 = column(
    minimal_css, sidebar_title, tour_start_btn,
    legend_div, divider(),
    address_input, crash_div, stats_div,
    Div(width=W, text='<p style="color:#555;font-size:10px;font-family:sans-serif;text-transform:uppercase;letter-spacing:0.05em;margin:10px 0 4px;">Click a dot to inspect</p>'),
    info_div1, divider(),
    Div(text='<p style="color:#555;font-size:11px;font-family:sans-serif;text-transform:uppercase;letter-spacing:0.05em;margin:10px 0 8px;font-weight:bold;">Filters</p>'),
    sel_year1, sel_state1, sel_drunk1, sel_ped1, sel_bike1, sel_age1, sel_norm1, hour_slider1,
    width=220, sizing_mode="fixed",
    styles={"background":DARK_BG,"padding":"16px 14px","overflow-y":"auto","height":"100vh","border-right":"1px solid #1e1e3a","box-sizing":"border-box"}
)

tab1_layout = row(sidebar1, p1, sizing_mode="stretch_both")

p_left,  p_right    = make_map(""), make_map("")
src_left, src_right = make_source(), make_source()

info_div_L = Div(width=180, text="", styles={"background":"#0d0d1a","border-radius":"8px","border":"1px solid #1e1e3a","padding":"0 10px","min-height":"300px","margin-top":"6px"})
info_div_R = Div(width=180, text="", styles={"background":"#0d0d1a","border-radius":"8px","border":"1px solid #1e1e3a","padding":"0 10px","min-height":"300px","margin-top":"6px"})
add_hover(p_left,  src_left,  info_div_L)
add_hover(p_right, src_right, info_div_R)

comp_state        = style(Select(title="State (Both Sides)", value="All", options=states), 200)
comp_search_input = style(TextInput(title="Search Map View", placeholder="Search both maps..."), 240)

def comp_search():
    addr = comp_search_input.value.strip()
    if not addr: return
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": addr, "format": "json", "limit": 1},
            headers={"User-Agent": "FARS-Map/1.0"}, timeout=5
        ).json()
        if res:
            lat, lon  = float(res[0]["lat"]), float(res[0]["lon"])
            xc = lon * (k * math.pi / 180)
            yc = math.log(math.tan((90 + lat) * math.pi / 360)) * k
            osm_type  = res[0].get("type","")
            osm_class = res[0].get("class","")
            if osm_type == "state":                                                 delta = 350000
            elif osm_class == "boundary" and osm_type == "administrative":         delta = 25000
            elif osm_type in ("suburb","neighbourhood","quarter","village","town"): delta = 10000
            else:                                                                   delta = 1500
            for px in [p_left, p_right]:
                px.x_range.update(start=xc-delta, end=xc+delta)
                px.y_range.update(start=yc-delta, end=yc+delta)
    except Exception as e:
        print(f"Comp search error: {e}")

comp_search_input.on_change("value", lambda a, o, n: comp_search())

sel_year_L  = style(Select(title="Year",         value=most_recent_year, options=years), 180)
sel_drunk_L = style(Select(title="Drunk Drivers", value="All", options=["All","Drunk Drivers Involved","No Drunk Drivers"]), 180)
sel_ped_L   = style(Select(title="Pedestrian",   value="All", options=["All","Pedestrian Involved","No Pedestrian"]), 180)
sel_bike_L  = style(Select(title="Cyclist",      value="All", options=["All","Cyclist Involved","No Cyclist"]), 180)
sel_age_L   = style(Select(title="Age Group",    value="All", options=["All","Child (0-15)","Youth (16-20)","Adult (21-59)","Older Adult (60+)"]), 180)
hour_L      = style(RangeSlider(start=0, end=23, value=(0,23), step=1, title="Hour Range"), 180)
hour_L.stylesheets.append(":host .bk-slider-title { color: #e0e0e0 !important; }")
count_L = Div(width=180, text="", styles={"color":"#e0e0e0","font-size":"12px","padding":"4px 8px","background":"#1a1a2e","border-radius":"12px","border":"1px solid #2a2a4a"})

trend_div = Div(width=110, text="", styles={"font-family":"sans-serif","padding":"8px 4px","text-align":"center"})
_comp_counts = {"left": 0, "right": 0}

def update_trend():
    l, r = _comp_counts["left"], _comp_counts["right"]
    if l == 0 or r == 0:
        trend_div.text = ""
        return
    pct = round((r - l) / l * 100, 1)
    if pct > 0:
        arrow, color, word = "&#9650;", "#ff4444", "more"
    elif pct < 0:
        arrow, color, word = "&#9660;", "#7bc67e", "fewer"
    else:
        arrow, color, word = "&#9654;", "#888", "same"
    yr_l = sel_year_L.value
    yr_r = sel_year_R.value
    trend_div.text = (
        f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:12px 6px;font-family:sans-serif;gap:6px;">'
        f'<span style="color:#666;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;">{yr_l}</span>'
        f'<span style="color:{color};font-size:28px;line-height:1;">{arrow}</span>'
        f'<span style="color:{color};font-size:18px;font-weight:700;line-height:1;">{abs(pct)}%</span>'
        f'<span style="color:{color};font-size:10px;">{word} crashes</span>'
        f'<span style="color:#666;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;">{yr_r}</span>'
        f'</div>'
    )

sel_year_R  = style(Select(title="Year",         value=second_year, options=years), 180)
sel_drunk_R = style(Select(title="Drunk Drivers", value="All", options=["All","Drunk Drivers Involved","No Drunk Drivers"]), 180)
sel_ped_R   = style(Select(title="Pedestrian",   value="All", options=["All","Pedestrian Involved","No Pedestrian"]), 180)
sel_bike_R  = style(Select(title="Cyclist",      value="All", options=["All","Cyclist Involved","No Cyclist"]), 180)
sel_age_R   = style(Select(title="Age Group",    value="All", options=["All","Child (0-15)","Youth (16-20)","Adult (21-59)","Older Adult (60+)"]), 180)
hour_R      = style(RangeSlider(start=0, end=23, value=(0,23), step=1, title="Hour Range"), 180)
hour_R.stylesheets.append(":host .bk-slider-title { color: #e0e0e0 !important; }")
count_R = Div(width=180, text="", styles={"color":"#e0e0e0","font-size":"12px","padding":"4px 8px","background":"#1a1a2e","border-radius":"12px","border":"1px solid #2a2a4a"})

def update_left(attr, old, new):
    t = filter_df(sel_year_L.value, comp_state.value, sel_drunk_L.value,
                  sel_ped_L.value, sel_bike_L.value, *hour_L.value,
                  age_val=sel_age_L.value)
    n, fatals = len(t), int(t["FATALS"].sum())
    count_L.text = (f'<b style="color:#ff8c00">{n:,}</b> crashes &nbsp;|&nbsp; <b style="color:#ff4444">{fatals:,}</b> fatalities')
    src_left.data     = to_source(t)
    p_left.title.text = f"{sel_year_L.value}  --  {comp_state.value}"
    _comp_counts["left"] = n
    update_trend()

def update_right(attr, old, new):
    t = filter_df(sel_year_R.value, comp_state.value, sel_drunk_R.value,
                  sel_ped_R.value, sel_bike_R.value, *hour_R.value,
                  age_val=sel_age_R.value)
    n, fatals = len(t), int(t["FATALS"].sum())
    count_R.text = (f'<b style="color:#ff8c00">{n:,}</b> crashes &nbsp;|&nbsp; <b style="color:#ff4444">{fatals:,}</b> fatalities')
    src_right.data     = to_source(t)
    p_right.title.text = f"{sel_year_R.value}  --  {comp_state.value}"
    _comp_counts["right"] = n
    update_trend()

def update_both(attr, old, new):
    update_left(attr, old, new)
    update_right(attr, old, new)

comp_state.on_change("value", update_both)
for w in [sel_year_L, sel_drunk_L, sel_ped_L, sel_bike_L, sel_age_L]:
    w.on_change("value", update_left)
hour_L.on_change("value_throttled", update_left)
for w in [sel_year_R, sel_drunk_R, sel_ped_R, sel_bike_R, sel_age_R]:
    w.on_change("value", update_right)
hour_R.on_change("value_throttled", update_right)

def panel_title(text, width=180):
    return Div(width=width, text=f'<p style="color:{TEXT_LIGHT};font-size:13px;font-weight:600;font-family:sans-serif;margin:0 0 8px;">{text}</p>')

left_panel = column(
    panel_title("Left Map"),
    sel_year_L, sel_drunk_L, sel_ped_L, sel_bike_L, sel_age_L, hour_L, count_L, info_div_L,
    width=200, sizing_mode="fixed",
    styles={"background":DARK_BG,"padding":"12px","border-right":"1px solid #1e1e3a","height":"100%","box-sizing":"border-box"}
)

right_panel = column(
    panel_title("Right Map"),
    sel_year_R, sel_drunk_R, sel_ped_R, sel_bike_R, sel_age_R, hour_R, count_R, info_div_R,
    width=200, sizing_mode="fixed",
    styles={"background":DARK_BG,"padding":"12px","border-left":"1px solid #1e1e3a","height":"100%","box-sizing":"border-box"}
)

state_row = row(
    comp_state, comp_search_input,
    sizing_mode="fixed",
    styles={"background":DARK_BG,"padding":"8px 16px","border-bottom":"1px solid #1e1e3a","gap":"20px"}
)

trend_panel = column(
    trend_div, width=120, sizing_mode="fixed",
    styles={"background":DARK_BG,"border-left":"1px solid #1e1e3a","border-right":"1px solid #1e1e3a",
            "height":"100%","display":"flex","align-items":"center","justify-content":"center","box-sizing":"border-box"}
)

maps_row    = row(left_panel, p_left, trend_panel, p_right, right_panel, sizing_mode="stretch_both")
tab2_layout = column(state_row, maps_row, sizing_mode="stretch_both")

chart_year  = style(Select(title="Year",  value=most_recent_year, options=["All"]+years), 200)
chart_state = style(Select(title="State", value="All",            options=states), 200)
chart_norm  = style(Select(title="State Ranking", value="Raw Count", options=["Raw Count","Per 100k People"]), 200)

def make_chart(title, height=280):
    p = figure(title=title, height=height, sizing_mode="stretch_width", tools="", toolbar_location=None)
    p.background_fill_color = "#1a1a2e"
    p.border_fill_color     = "#0d0d1a"
    p.outline_line_color    = "#2a2a4a"
    p.title.text_color      = "#e0e0e0"
    p.title.text_font_size  = "12pt"
    p.xaxis.major_label_text_color = "#888"
    p.yaxis.major_label_text_color = "#888"
    p.xaxis.axis_line_color = "#2a2a4a"
    p.yaxis.axis_line_color = "#2a2a4a"
    p.xgrid.grid_line_color = "#1e1e3a"
    p.ygrid.grid_line_color = "#1e1e3a"
    return p

age_groups  = ["Child (0-15)","Youth (16-20)","Adult (21-59)","Older Adult (60+)"]
age_colors  = ["#ff6b9d","#c77dff","#4a90d9","#f5a623"]
init_states = states[1:16] if len(states) > 15 else states[1:]

ph = make_chart("Crashes by Hour of Day")
ph.xaxis.axis_label = "Hour"
ph.yaxis.axis_label = "Crashes"
src_hour = ColumnDataSource(data=dict(x=[], top=[]))
ph.vbar(x="x", top="top", width=0.8, source=src_hour, color="#4a90d9", alpha=0.8)

py = make_chart("Crashes by Year")
py.xaxis.axis_label = "Year"
py.yaxis.axis_label = "Crashes"
src_year_chart = ColumnDataSource(data=dict(x=[], y=[]))
py.line(x="x", y="y", source=src_year_chart, color="#f5c842", line_width=2)
py.scatter(x="x", y="y", source=src_year_chart, color="#f5c842", size=7)

ps = figure(title="Top 15 States by Crashes", height=320, sizing_mode="stretch_width",
            x_range=FactorRange(factors=init_states), tools="", toolbar_location=None)
ps.background_fill_color = "#1a1a2e"
ps.border_fill_color     = "#0d0d1a"
ps.outline_line_color    = "#2a2a4a"
ps.title.text_color      = "#e0e0e0"
ps.title.text_font_size  = "12pt"
ps.xaxis.major_label_text_color = "#888"
ps.yaxis.major_label_text_color = "#888"
ps.xaxis.axis_line_color = "#2a2a4a"
ps.yaxis.axis_line_color = "#2a2a4a"
ps.xgrid.grid_line_color = "#1e1e3a"
ps.ygrid.grid_line_color = "#1e1e3a"
ps.xaxis.axis_label      = "State"
ps.xaxis.major_label_orientation = 1.0
src_state_chart = ColumnDataSource(data=dict(x=init_states, top=[0]*len(init_states)))
ps.vbar(x="x", top="top", width=0.8, source=src_state_chart, color="#7bc67e", alpha=0.8)

pa = figure(title="Crashes by Age Group", height=280, sizing_mode="stretch_width",
            x_range=FactorRange(factors=age_groups), tools="", toolbar_location=None)
pa.background_fill_color = "#1a1a2e"
pa.border_fill_color     = "#0d0d1a"
pa.outline_line_color    = "#2a2a4a"
pa.title.text_color      = "#e0e0e0"
pa.title.text_font_size  = "12pt"
pa.xaxis.major_label_text_color = "#888"
pa.yaxis.major_label_text_color = "#888"
pa.xaxis.axis_line_color = "#2a2a4a"
pa.yaxis.axis_line_color = "#2a2a4a"
pa.xgrid.grid_line_color = "#1e1e3a"
pa.ygrid.grid_line_color = "#1e1e3a"
pa.xaxis.axis_label      = "Age Group"
pa.yaxis.axis_label      = "Crashes"
src_age = ColumnDataSource(data=dict(x=age_groups, top=[0]*4, color=age_colors))
pa.vbar(x="x", top="top", width=0.6, source=src_age, color="color", alpha=0.85)

def update_charts(attr, old, new):
    yr = chart_year.value
    st = chart_state.value
    if yr == "All":
        t = df
    else:
        t = df_by_year.get(int(yr), df.iloc[0:0])
    if st != "All":
        t = t[t["STATE_NAME"] == st]
    t_valid = t[t["HOUR"] < 99]
    if len(t_valid) > 0:
        hour_counts = t_valid["HOUR"].value_counts().sort_index()
        src_hour.data = dict(x=hour_counts.index.tolist(), top=hour_counts.values.tolist())
    else:
        src_hour.data = dict(x=[], top=[])
    if yr == "All":
        year_counts = t.groupby("YEAR_STR")["ST_CASE"].count().sort_index()
        src_year_chart.data = dict(x=year_counts.index.tolist(), y=year_counts.values.tolist())
        py.visible = True
    else:
        py.visible = False
    if st == "All":
        norm_mode = chart_norm.value
        if norm_mode == "Per 100k People":
            state_counts_raw = t["STATE_NAME"].value_counts()
            per100k = {}
            for state, cnt in state_counts_raw.items():
                pop = STATE_POP.get(state, None)
                if pop and pop > 0:
                    per100k[state] = round(cnt / pop * 100000, 2)
            per100k_series = pd.Series(per100k).sort_values(ascending=False).head(15)
            new_states = per100k_series.index.tolist()
            new_tops   = per100k_series.values.tolist()
            ps.title.text       = "Top 15 States by Crashes (per 100k people)"
            ps.yaxis.axis_label = "Crashes per 100k"
        else:
            state_counts = t["STATE_NAME"].value_counts().head(15).sort_values(ascending=False)
            new_states   = state_counts.index.tolist()
            new_tops     = state_counts.values.tolist()
            ps.title.text       = "Top 15 States by Crashes"
            ps.yaxis.axis_label = "Crashes"
        if new_states:
            ps.x_range.factors   = new_states
            src_state_chart.data = dict(x=new_states, top=new_tops)
        ps.visible = True
    else:
        ps.visible = False
    age_vals = [int(t["HAS_CHILD"].sum()), int(t["HAS_YOUTH"].sum()),
                int(t["HAS_ADULT"].sum()), int(t["HAS_OLDER"].sum())]
    src_age.data = dict(x=age_groups, top=age_vals, color=age_colors)

chart_year.on_change("value",  update_charts)
chart_state.on_change("value", update_charts)
chart_norm.on_change("value",  update_charts)

chart_sidebar = column(
    Div(width=200, text=f'<div style="padding:4px 0 12px;border-bottom:1px solid #1e1e3a;font-family:sans-serif;"><p style="color:{TEXT_LIGHT};font-size:14px;font-weight:600;margin:0 0 2px;">Charts</p><p style="color:{TEXT_DIM};font-size:11px;margin:0;">Filter the data below</p></div>'),
    chart_year, chart_state, chart_norm,
    width=220, sizing_mode="fixed",
    styles={"background":DARK_BG,"padding":"16px 14px","overflow-y":"auto","height":"100vh","border-right":"1px solid #1e1e3a","box-sizing":"border-box"}
)

chart_grid = column(
    row(ph, py, sizing_mode="stretch_width"),
    row(pa, sizing_mode="stretch_width"),
    ps,
    sizing_mode="stretch_both",
    styles={"padding":"16px","background":DARK_BG,"overflow-y":"auto"}
)

tab3_layout = row(chart_sidebar, chart_grid, sizing_mode="stretch_both")

tab1 = TabPanel(child=tab1_layout, title="Heatmap")
tab2 = TabPanel(child=tab2_layout, title="Year Comparison")
tab3 = TabPanel(child=tab3_layout, title="Charts")
tab4 = TabPanel(child=tour_layout, title="Tour")
tabs = Tabs(tabs=[tab1, tab2, tab3, tab4], sizing_mode="stretch_both")

tour_tabs_ref[0] = tabs

update1("", None, None)
update_left("", None, None)
update_right("", None, None)
update_charts("", None, None)

LOADING_TEMPLATE = Template("""
{% extends base %}
{% block postamble %}
<style>
  #fars-loader {
    position: fixed; inset: 0; z-index: 99999;
    background: #0d0d1a;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: Calibri, sans-serif;
    transition: opacity 0.6s ease;
  }
  #fars-loader.fade-out { opacity: 0; pointer-events: none; }
  .loader-dot-row { display: flex; gap: 10px; margin-bottom: 36px; }
  .loader-dot { width: 14px; height: 14px; border-radius: 50%; animation: loader-bounce 1.2s infinite ease-in-out; }
  .loader-dot:nth-child(1) { background: #ff4444; animation-delay: 0s; }
  .loader-dot:nth-child(2) { background: #ffd700; animation-delay: 0.15s; }
  .loader-dot:nth-child(3) { background: #00d4ff; animation-delay: 0.3s; }
  .loader-dot:nth-child(4) { background: #ff8c00; animation-delay: 0.45s; }
  @keyframes loader-bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1.2); opacity: 1; } }
  .loader-title { color: #e0e0e0; font-size: 22px; font-weight: 600; margin: 0 0 10px; letter-spacing: 0.04em; }
  .loader-sub   { color: #444; font-size: 13px; margin: 0 0 32px; letter-spacing: 0.06em; text-transform: uppercase; }
  .loader-bar-track { width: 260px; height: 3px; background: #1e1e3a; border-radius: 4px; overflow: hidden; }
  .loader-bar-fill  { height: 100%; width: 0%; background: #4a90d9; border-radius: 4px; animation: loader-bar 2.5s ease-in-out forwards; }
  @keyframes loader-bar { 0% { width: 0%; } 40% { width: 60%; } 80% { width: 85%; } 100% { width: 92%; } }
  .loader-url { margin-top: 40px; color: #2a2a4a; font-size: 12px; letter-spacing: 0.08em; }
</style>
<div id="fars-loader">
  <div class="loader-dot-row">
    <div class="loader-dot"></div><div class="loader-dot"></div>
    <div class="loader-dot"></div><div class="loader-dot"></div>
  </div>
  <p class="loader-title">FARS Crash Map</p>
  <p class="loader-sub">Loading 800,000+ crashes&hellip;</p>
  <div class="loader-bar-track"><div class="loader-bar-fill"></div></div>
  <p class="loader-url">usaccidentheatmap.org</p>
</div>
<script>
  document.addEventListener("DOMContentLoaded", function () {
    function dismissLoader() {
      var el = document.getElementById("fars-loader");
      if (!el) return;
      el.classList.add("fade-out");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 700);
    }
    var checkInterval = setInterval(function () {
      var canvas = document.querySelector(".bk-root canvas");
      var tabs   = document.querySelector(".bk-root .bk-tabs-header");
      if (canvas && tabs) { clearInterval(checkInterval); setTimeout(dismissLoader, 600); }
    }, 300);
    setTimeout(dismissLoader, 12000);
  });
</script>
{% endblock %}
""")

curdoc().template = LOADING_TEMPLATE
curdoc().add_root(tabs)
curdoc().title = "FARS Map"
#testing 