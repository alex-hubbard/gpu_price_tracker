#!/usr/bin/env python3
"""Build / refresh `data/regions.csv` from embedded mappings + the actual data.

Strategy
--------
- Discover every distinct `(provider, raw_region)` pair currently present
  in the local Parquet tree (or the source SQLite, if `--db` is given).
- For each, look up canonical fields from the dictionaries embedded below.
- Preserve any hand-edited rows already in `data/regions.csv` — those win.
- Write the merged result back to `data/regions.csv` sorted by
  `(provider, raw_region)`.

The runtime path (`regions.py`) reads the CSV. This script is for
maintenance: re-run after new providers/regions show up to discover them
and fill in defaults.

Usage
-----
    python3 scripts/build_regions_csv.py
    python3 scripts/build_regions_csv.py --src data/parquet/prices --out data/regions.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

import duckdb


CSV_FIELDS = [
    "provider",
    "raw_region",
    "region_canonical",
    "country",
    "lat",
    "lon",
    "region_group",
]


# ---- Group catalogue --------------------------------------------------------

GROUP_NA_E = "North America East"
GROUP_NA_C = "North America Central"
GROUP_NA_W = "North America West"
GROUP_SA = "South America"
GROUP_EU_W = "Europe West"
GROUP_EU_C = "Europe Central"
GROUP_EU_N = "Europe North"
GROUP_EU_S = "Europe South"
GROUP_ME = "Middle East"
GROUP_AF = "Africa"
GROUP_AP_S = "APAC South"
GROUP_AP_E = "APAC East"
GROUP_AP_SE = "APAC Southeast"
GROUP_GOV = "GovCloud"


# ---- Country code → (name, lat, lon) for Vast.ai / Runpod / etc. ------------
# Used only as a fallback when a marketplace provider exposes a 2-letter
# ISO country code as its "region" string. Coordinates are approximate
# country centroids.
COUNTRY = {
    "US": ("US", 39.83, -98.58, GROUP_NA_C),
    "CA": ("CA", 56.13, -106.35, GROUP_NA_C),
    "MX": ("MX", 23.63, -102.55, GROUP_NA_C),
    "BR": ("BR", -14.24, -51.93, GROUP_SA),
    "CL": ("CL", -35.68, -71.54, GROUP_SA),
    "AR": ("AR", -38.42, -63.62, GROUP_SA),
    "CO": ("CO", 4.57, -74.30, GROUP_SA),
    "PE": ("PE", -9.19, -75.02, GROUP_SA),
    "GB": ("GB", 55.38, -3.44, GROUP_EU_W),
    "UK": ("GB", 55.38, -3.44, GROUP_EU_W),
    "IE": ("IE", 53.41, -8.24, GROUP_EU_W),
    "FR": ("FR", 46.23, 2.21, GROUP_EU_W),
    "NL": ("NL", 52.13, 5.29, GROUP_EU_W),
    "BE": ("BE", 50.50, 4.47, GROUP_EU_W),
    "DE": ("DE", 51.17, 10.45, GROUP_EU_C),
    "PL": ("PL", 51.92, 19.15, GROUP_EU_C),
    "CZ": ("CZ", 49.82, 15.47, GROUP_EU_C),
    "AT": ("AT", 47.52, 14.55, GROUP_EU_C),
    "CH": ("CH", 46.82, 8.23, GROUP_EU_C),
    "HU": ("HU", 47.16, 19.50, GROUP_EU_C),
    "RO": ("RO", 45.94, 24.97, GROUP_EU_C),
    "SK": ("SK", 48.67, 19.70, GROUP_EU_C),
    "DK": ("DK", 56.26, 9.50, GROUP_EU_N),
    "SE": ("SE", 60.13, 18.64, GROUP_EU_N),
    "NO": ("NO", 60.47, 8.47, GROUP_EU_N),
    "FI": ("FI", 61.92, 25.75, GROUP_EU_N),
    "IS": ("IS", 64.96, -19.02, GROUP_EU_N),
    "EE": ("EE", 58.60, 25.01, GROUP_EU_N),
    "LV": ("LV", 56.88, 24.60, GROUP_EU_N),
    "LT": ("LT", 55.17, 23.88, GROUP_EU_N),
    "ES": ("ES", 40.46, -3.75, GROUP_EU_S),
    "PT": ("PT", 39.40, -8.22, GROUP_EU_S),
    "IT": ("IT", 41.87, 12.57, GROUP_EU_S),
    "GR": ("GR", 39.07, 21.82, GROUP_EU_S),
    "TR": ("TR", 38.96, 35.24, GROUP_EU_S),
    "BG": ("BG", 42.73, 25.49, GROUP_EU_S),
    "HR": ("HR", 45.10, 15.20, GROUP_EU_S),
    "RS": ("RS", 44.02, 21.01, GROUP_EU_S),
    "SI": ("SI", 46.15, 14.99, GROUP_EU_S),
    "RU": ("RU", 61.52, 105.32, GROUP_EU_C),
    "UA": ("UA", 48.38, 31.17, GROUP_EU_C),
    "BY": ("BY", 53.71, 27.95, GROUP_EU_C),
    "MD": ("MD", 47.41, 28.37, GROUP_EU_C),
    "AE": ("AE", 23.42, 53.85, GROUP_ME),
    "IL": ("IL", 31.05, 34.85, GROUP_ME),
    "SA": ("SA", 23.89, 45.08, GROUP_ME),
    "QA": ("QA", 25.35, 51.18, GROUP_ME),
    "BH": ("BH", 26.07, 50.55, GROUP_ME),
    "JO": ("JO", 30.59, 36.24, GROUP_ME),
    "ZA": ("ZA", -30.56, 22.94, GROUP_AF),
    "EG": ("EG", 26.82, 30.80, GROUP_AF),
    "NG": ("NG", 9.08, 8.68, GROUP_AF),
    "KE": ("KE", -0.02, 37.91, GROUP_AF),
    "MA": ("MA", 31.79, -7.09, GROUP_AF),
    "IN": ("IN", 20.59, 78.96, GROUP_AP_S),
    "PK": ("PK", 30.38, 69.35, GROUP_AP_S),
    "BD": ("BD", 23.68, 90.36, GROUP_AP_S),
    "LK": ("LK", 7.87, 80.77, GROUP_AP_S),
    "NP": ("NP", 28.39, 84.12, GROUP_AP_S),
    "JP": ("JP", 36.20, 138.25, GROUP_AP_E),
    "KR": ("KR", 35.91, 127.77, GROUP_AP_E),
    "CN": ("CN", 35.86, 104.20, GROUP_AP_E),
    "TW": ("TW", 23.70, 120.96, GROUP_AP_E),
    "HK": ("HK", 22.32, 114.17, GROUP_AP_E),
    "MN": ("MN", 46.86, 103.85, GROUP_AP_E),
    "SG": ("SG", 1.35, 103.82, GROUP_AP_SE),
    "MY": ("MY", 4.21, 101.98, GROUP_AP_SE),
    "ID": ("ID", -0.79, 113.92, GROUP_AP_SE),
    "TH": ("TH", 15.87, 100.99, GROUP_AP_SE),
    "VN": ("VN", 14.06, 108.28, GROUP_AP_SE),
    "PH": ("PH", 12.88, 121.77, GROUP_AP_SE),
    "AU": ("AU", -25.27, 133.78, GROUP_AP_SE),
    "NZ": ("NZ", -40.90, 174.89, GROUP_AP_SE),
    # Less-common codes seen in marketplace listings.
    "BA": ("BA", 43.92, 17.68, GROUP_EU_S),
    "KZ": ("KZ", 48.02, 66.92, GROUP_AP_E),
    "MK": ("MK", 41.61, 21.75, GROUP_EU_S),
    "MO": ("MO", 22.20, 113.54, GROUP_AP_E),
    "TT": ("TT", 10.69, -61.22, GROUP_SA),
    "FIN": ("FI", 61.92, 25.75, GROUP_EU_N),  # Verda's "FIN-01" prefix
}


# ---- AWS --------------------------------------------------------------------
AWS = {
    "us-east-1": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "us-east-2": ("us-east-ohio", "US", 40.41, -82.91, GROUP_NA_E),
    "us-west-1": ("us-west-california", "US", 37.35, -121.96, GROUP_NA_W),
    "us-west-2": ("us-west-oregon", "US", 45.84, -119.70, GROUP_NA_W),
    "ca-central-1": ("ca-central-quebec", "CA", 45.50, -73.50, GROUP_NA_E),
    "ca-west-1": ("ca-west-calgary", "CA", 51.05, -114.07, GROUP_NA_W),
    "mx-central-1": ("mx-central-mexico", "MX", 19.43, -99.13, GROUP_NA_C),
    "sa-east-1": ("sa-east-saopaulo", "BR", -23.55, -46.63, GROUP_SA),
    "eu-west-1": ("eu-west-ireland", "IE", 53.35, -6.26, GROUP_EU_W),
    "eu-west-2": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "eu-west-3": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "eu-central-1": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "eu-central-2": ("eu-central-zurich", "CH", 47.37, 8.55, GROUP_EU_C),
    "eu-north-1": ("eu-north-stockholm", "SE", 59.33, 18.07, GROUP_EU_N),
    "eu-south-1": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "eu-south-2": ("eu-south-spain", "ES", 40.42, -3.70, GROUP_EU_S),
    "ap-east-1": ("ap-east-hongkong", "HK", 22.32, 114.17, GROUP_AP_E),
    "ap-south-1": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "ap-south-2": ("ap-south-hyderabad", "IN", 17.39, 78.49, GROUP_AP_S),
    "ap-northeast-1": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "ap-northeast-2": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "ap-northeast-3": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "ap-southeast-1": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "ap-southeast-2": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
    "ap-southeast-3": ("ap-southeast-jakarta", "ID", -6.21, 106.85, GROUP_AP_SE),
    "ap-southeast-4": ("ap-southeast-melbourne", "AU", -37.81, 144.96, GROUP_AP_SE),
    "ap-southeast-5": ("ap-southeast-malaysia", "MY", 3.14, 101.69, GROUP_AP_SE),
    "ap-southeast-7": ("ap-southeast-bangkok", "TH", 13.75, 100.50, GROUP_AP_SE),
    "af-south-1": ("af-south-capetown", "ZA", -33.92, 18.42, GROUP_AF),
    "me-central-1": ("me-central-uae", "AE", 25.27, 55.31, GROUP_ME),
    "me-south-1": ("me-south-bahrain", "BH", 26.07, 50.55, GROUP_ME),
    "il-central-1": ("il-central-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "us-gov-east-1": ("us-gov-east", "US", 38.13, -78.45, GROUP_GOV),
    "us-gov-west-1": ("us-gov-west", "US", 45.84, -119.70, GROUP_GOV),
    "ap-east-2": ("ap-east-taiwan", "TW", 23.70, 120.96, GROUP_AP_E),
    "ap-southeast-6": ("ap-southeast-newzealand", "NZ", -36.85, 174.76, GROUP_AP_SE),
}


# ---- GCP --------------------------------------------------------------------
GCP = {
    "us-east1": ("us-east-southcarolina", "US", 33.84, -81.16, GROUP_NA_E),
    "us-east4": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "us-east5": ("us-east-ohio", "US", 39.96, -82.99, GROUP_NA_E),
    "us-east7": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "us-central1": ("us-central-iowa", "US", 41.88, -93.10, GROUP_NA_C),
    "us-central2": ("us-central-oklahoma", "US", 35.47, -97.52, GROUP_NA_C),
    "us-west1": ("us-west-oregon", "US", 45.84, -119.70, GROUP_NA_W),
    "us-west2": ("us-west-losangeles", "US", 34.05, -118.24, GROUP_NA_W),
    "us-west3": ("us-west-saltlakecity", "US", 40.76, -111.89, GROUP_NA_W),
    "us-west4": ("us-west-lasvegas", "US", 36.17, -115.14, GROUP_NA_W),
    "us-west8": ("us-west-arizona", "US", 33.45, -112.07, GROUP_NA_W),
    "us-south1": ("us-south-dallas", "US", 32.78, -96.80, GROUP_NA_C),
    "northamerica-northeast1": ("ca-east-montreal", "CA", 45.50, -73.57, GROUP_NA_E),
    "northamerica-northeast2": ("ca-east-toronto", "CA", 43.65, -79.38, GROUP_NA_E),
    "northamerica-south1": ("mx-central-mexico", "MX", 19.43, -99.13, GROUP_NA_C),
    "southamerica-east1": ("sa-east-saopaulo", "BR", -23.55, -46.63, GROUP_SA),
    "southamerica-west1": ("sa-west-santiago", "CL", -33.45, -70.66, GROUP_SA),
    "europe-west1": ("eu-west-belgium", "BE", 50.50, 4.47, GROUP_EU_W),
    "europe-west2": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "europe-west3": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "europe-west4": ("eu-west-netherlands", "NL", 52.37, 4.90, GROUP_EU_W),
    "europe-west6": ("eu-central-zurich", "CH", 47.37, 8.55, GROUP_EU_C),
    "europe-west8": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "europe-west9": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "europe-west10": ("eu-central-berlin", "DE", 52.52, 13.40, GROUP_EU_C),
    "europe-west12": ("eu-south-turin", "IT", 45.07, 7.69, GROUP_EU_S),
    "europe-north1": ("eu-north-finland", "FI", 60.55, 27.18, GROUP_EU_N),
    "europe-north2": ("eu-north-stockholm", "SE", 59.33, 18.07, GROUP_EU_N),
    "europe-southwest1": ("eu-south-madrid", "ES", 40.42, -3.70, GROUP_EU_S),
    "europe-central2": ("eu-central-warsaw", "PL", 52.23, 21.01, GROUP_EU_C),
    "asia-east1": ("ap-east-taiwan", "TW", 24.15, 120.69, GROUP_AP_E),
    "asia-east2": ("ap-east-hongkong", "HK", 22.32, 114.17, GROUP_AP_E),
    "asia-northeast1": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "asia-northeast2": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "asia-northeast3": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "asia-south1": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "asia-south2": ("ap-south-delhi", "IN", 28.61, 77.21, GROUP_AP_S),
    "asia-southeast1": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "asia-southeast2": ("ap-southeast-jakarta", "ID", -6.21, 106.85, GROUP_AP_SE),
    "australia-southeast1": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
    "australia-southeast2": ("ap-southeast-melbourne", "AU", -37.81, 144.96, GROUP_AP_SE),
    "asia-southeast3": ("ap-southeast-bangkok", "TH", 13.75, 100.50, GROUP_AP_SE),
    "me-central1": ("me-central-doha", "QA", 25.35, 51.18, GROUP_ME),
    "me-central2": ("me-central-dammam", "SA", 26.39, 49.98, GROUP_ME),
    "me-west1": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "africa-south1": ("af-south-johannesburg", "ZA", -26.20, 28.05, GROUP_AF),
}


# ---- Azure ------------------------------------------------------------------
AZURE = {
    "eastus": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "eastus2": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "eastus3": ("us-east-atlanta", "US", 33.75, -84.39, GROUP_NA_E),
    "eastusslv": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "westus": ("us-west-california", "US", 37.35, -121.96, GROUP_NA_W),
    "westus2": ("us-west-washington", "US", 47.61, -122.33, GROUP_NA_W),
    "westus3": ("us-west-arizona", "US", 33.45, -112.07, GROUP_NA_W),
    "centralus": ("us-central-iowa", "US", 41.88, -93.10, GROUP_NA_C),
    "northcentralus": ("us-north-illinois", "US", 41.88, -87.63, GROUP_NA_C),
    "southcentralus": ("us-south-texas", "US", 29.42, -98.49, GROUP_NA_C),
    "westcentralus": ("us-west-wyoming", "US", 41.16, -104.82, GROUP_NA_W),
    "canadacentral": ("ca-central-toronto", "CA", 43.65, -79.38, GROUP_NA_E),
    "canadaeast": ("ca-east-quebec", "CA", 46.81, -71.21, GROUP_NA_E),
    "mexicocentral": ("mx-central-mexico", "MX", 19.43, -99.13, GROUP_NA_C),
    "brazilsouth": ("sa-south-saopaulo", "BR", -23.55, -46.63, GROUP_SA),
    "brazilsoutheast": ("sa-southeast-rio", "BR", -22.91, -43.17, GROUP_SA),
    "westeurope": ("eu-west-netherlands", "NL", 52.37, 4.90, GROUP_EU_W),
    "northeurope": ("eu-north-ireland", "IE", 53.35, -6.26, GROUP_EU_W),
    "uksouth": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "ukwest": ("eu-west-cardiff", "GB", 51.48, -3.18, GROUP_EU_W),
    "francecentral": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "francesouth": ("eu-south-marseille", "FR", 43.30, 5.37, GROUP_EU_S),
    "germanywestcentral": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "germanynorth": ("eu-central-berlin", "DE", 52.52, 13.40, GROUP_EU_C),
    "swedencentral": ("eu-north-sweden", "SE", 60.13, 18.64, GROUP_EU_N),
    "norwayeast": ("eu-north-oslo", "NO", 59.91, 10.75, GROUP_EU_N),
    "norwaywest": ("eu-north-stavanger", "NO", 58.97, 5.73, GROUP_EU_N),
    "switzerlandnorth": ("eu-central-zurich", "CH", 47.37, 8.55, GROUP_EU_C),
    "switzerlandwest": ("eu-central-geneva", "CH", 46.20, 6.15, GROUP_EU_C),
    "italynorth": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "spaincentral": ("eu-south-madrid", "ES", 40.42, -3.70, GROUP_EU_S),
    "polandcentral": ("eu-central-warsaw", "PL", 52.23, 21.01, GROUP_EU_C),
    "austriaeast": ("eu-central-vienna", "AT", 48.21, 16.37, GROUP_EU_C),
    "chilecentral": ("sa-west-santiago", "CL", -33.45, -70.66, GROUP_SA),
    "southafricanorth": ("af-north-johannesburg", "ZA", -26.20, 28.05, GROUP_AF),
    "southafricawest": ("af-south-capetown", "ZA", -33.92, 18.42, GROUP_AF),
    "uaenorth": ("me-central-dubai", "AE", 25.27, 55.31, GROUP_ME),
    "uaecentral": ("me-central-abudhabi", "AE", 24.47, 54.37, GROUP_ME),
    "qatarcentral": ("me-central-doha", "QA", 25.35, 51.18, GROUP_ME),
    "israelcentral": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "southindia": ("ap-south-chennai", "IN", 13.08, 80.27, GROUP_AP_S),
    "westindia": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "centralindia": ("ap-south-pune", "IN", 18.52, 73.85, GROUP_AP_S),
    "jioindiacentral": ("ap-south-pune", "IN", 18.52, 73.85, GROUP_AP_S),
    "jioindiawest": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "eastasia": ("ap-east-hongkong", "HK", 22.32, 114.17, GROUP_AP_E),
    "southeastasia": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "japaneast": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "japanwest": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "koreacentral": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "koreasouth": ("ap-northeast-busan", "KR", 35.18, 129.08, GROUP_AP_E),
    "australiaeast": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
    "australiasoutheast": ("ap-southeast-melbourne", "AU", -37.81, 144.96, GROUP_AP_SE),
    "australiacentral": ("ap-southeast-canberra", "AU", -35.28, 149.13, GROUP_AP_SE),
    "australiacentral2": ("ap-southeast-canberra", "AU", -35.28, 149.13, GROUP_AP_SE),
    "newzealandnorth": ("ap-southeast-auckland", "NZ", -36.85, 174.76, GROUP_AP_SE),
    "indonesiacentral": ("ap-southeast-jakarta", "ID", -6.21, 106.85, GROUP_AP_SE),
    "malaysiawest": ("ap-southeast-kualalumpur", "MY", 3.14, 101.69, GROUP_AP_SE),
    "swedensouth": ("eu-north-sweden", "SE", 60.13, 18.64, GROUP_EU_N),
    "portland": ("us-west-oregon", "US", 45.52, -122.68, GROUP_NA_W),
    "belgiumcentral": ("eu-west-belgium", "BE", 50.85, 4.35, GROUP_EU_W),
    "denmarkeast": ("eu-north-copenhagen", "DK", 55.68, 12.57, GROUP_EU_N),
    "israelnorthwest": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "sgxsingapore1": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "usgovarizona": ("us-gov-arizona", "US", 33.45, -112.07, GROUP_GOV),
    "usgovtexas": ("us-gov-texas", "US", 32.78, -96.80, GROUP_GOV),
    "usgovvirginia": ("us-gov-virginia", "US", 38.13, -78.45, GROUP_GOV),
    # AT&T edge zones — geo-locate to the named city, group with their parent
    # region to keep them out of the main NA-East/NA-West buckets.
    "attatlanta1": ("us-east-atlanta-att", "US", 33.75, -84.39, GROUP_NA_E),
    "attdallas1": ("us-south-dallas-att", "US", 32.78, -96.80, GROUP_NA_C),
    "attdetroit1": ("us-east-detroit-att", "US", 42.33, -83.05, GROUP_NA_E),
    "attnewyork1": ("us-east-newyork-att", "US", 40.71, -74.01, GROUP_NA_E),
}


# ---- Vultr (IATA airport codes) --------------------------------------------
VULTR = {
    "ams": ("eu-west-amsterdam", "NL", 52.37, 4.90, GROUP_EU_W),
    "atl": ("us-east-atlanta", "US", 33.75, -84.39, GROUP_NA_E),
    "blr": ("ap-south-bangalore", "IN", 12.97, 77.59, GROUP_AP_S),
    "bom": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "cdg": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "dfw": ("us-south-dallas", "US", 32.78, -96.80, GROUP_NA_C),
    "ewr": ("us-east-newjersey", "US", 40.69, -74.17, GROUP_NA_E),
    "fra": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "hnl": ("us-west-honolulu", "US", 21.31, -157.86, GROUP_NA_W),
    "icn": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "itm": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "jnb": ("af-south-johannesburg", "ZA", -26.20, 28.05, GROUP_AF),
    "lax": ("us-west-losangeles", "US", 34.05, -118.24, GROUP_NA_W),
    "lhr": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "mad": ("eu-south-madrid", "ES", 40.42, -3.70, GROUP_EU_S),
    "man": ("eu-west-manchester", "GB", 53.48, -2.24, GROUP_EU_W),
    "mel": ("ap-southeast-melbourne", "AU", -37.81, 144.96, GROUP_AP_SE),
    "mex": ("mx-central-mexico", "MX", 19.43, -99.13, GROUP_NA_C),
    "mia": ("us-east-miami", "US", 25.76, -80.19, GROUP_NA_E),
    "nrt": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "ord": ("us-central-chicago", "US", 41.88, -87.63, GROUP_NA_C),
    "sao": ("sa-east-saopaulo", "BR", -23.55, -46.63, GROUP_SA),
    "scl": ("sa-west-santiago", "CL", -33.45, -70.66, GROUP_SA),
    "sea": ("us-west-seattle", "US", 47.61, -122.33, GROUP_NA_W),
    "sgp": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "sjc": ("us-west-california", "US", 37.34, -121.89, GROUP_NA_W),
    "sto": ("eu-north-stockholm", "SE", 59.33, 18.07, GROUP_EU_N),
    "syd": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
    "tlv": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "waw": ("eu-central-warsaw", "PL", 52.23, 21.01, GROUP_EU_C),
    "yto": ("ca-central-toronto", "CA", 43.65, -79.38, GROUP_NA_E),
    "del": ("ap-south-delhi", "IN", 28.61, 77.21, GROUP_AP_S),
}


# ---- Lambda Labs ------------------------------------------------------------
LAMBDA = {
    "us-east-1": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "us-east-2": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "us-east-3": ("us-east-newyork", "US", 40.71, -74.01, GROUP_NA_E),
    "us-midwest-1": ("us-central-illinois", "US", 41.88, -87.63, GROUP_NA_C),
    "us-south-1": ("us-south-texas", "US", 32.78, -96.80, GROUP_NA_C),
    "us-south-2": ("us-south-texas", "US", 32.78, -96.80, GROUP_NA_C),
    "us-south-3": ("us-south-texas", "US", 32.78, -96.80, GROUP_NA_C),
    "us-west-1": ("us-west-california", "US", 37.34, -121.89, GROUP_NA_W),
    "us-west-2": ("us-west-arizona", "US", 33.45, -112.07, GROUP_NA_W),
    "us-west-3": ("us-west-utah", "US", 40.76, -111.89, GROUP_NA_W),
    "europe-central-1": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "europe-west-1": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "asia-northeast-1": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "asia-northeast-2": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "asia-south-1": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "asia-southeast-1": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "me-west-1": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
    "australia-east-1": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
}


# ---- Nebius (compact GCP-like names) ---------------------------------------
NEBIUS = {
    "eu-north1": ("eu-north-finland", "FI", 60.55, 27.18, GROUP_EU_N),
    "eu-west1": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "me-west1": ("me-west-telaviv", "IL", 32.08, 34.78, GROUP_ME),
}


# ---- Verda (Finland) -------------------------------------------------------
VERDA = {
    "FIN-01": ("eu-north-finland", "FI", 61.92, 25.75, GROUP_EU_N),
    "FIN-02": ("eu-north-finland", "FI", 61.92, 25.75, GROUP_EU_N),
    "FIN-03": ("eu-north-finland", "FI", 61.92, 25.75, GROUP_EU_N),
}


# ---- OCI --------------------------------------------------------------------
OCI = {
    "US-ASHBURN-1": ("us-east-virginia", "US", 38.13, -78.45, GROUP_NA_E),
    "US-CHICAGO-1": ("us-central-chicago", "US", 41.88, -87.63, GROUP_NA_C),
    "US-PHOENIX-1": ("us-west-arizona", "US", 33.45, -112.07, GROUP_NA_W),
    "US-SANJOSE-1": ("us-west-california", "US", 37.34, -121.89, GROUP_NA_W),
    "US-LANGLEY-1": ("us-gov-langley", "US", 38.96, -77.21, GROUP_GOV),
    "US-LUKE-1": ("us-gov-luke", "US", 33.53, -112.39, GROUP_GOV),
    "US-GOV-ASHBURN-1": ("us-gov-east", "US", 38.13, -78.45, GROUP_GOV),
    "US-GOV-CHICAGO-1": ("us-gov-central", "US", 41.88, -87.63, GROUP_GOV),
    "US-GOV-PHOENIX-1": ("us-gov-west", "US", 33.45, -112.07, GROUP_GOV),
    "CA-MONTREAL-1": ("ca-central-quebec", "CA", 45.50, -73.57, GROUP_NA_E),
    "CA-TORONTO-1": ("ca-central-toronto", "CA", 43.65, -79.38, GROUP_NA_E),
    "MX-QUERETARO-1": ("mx-central-queretaro", "MX", 20.59, -100.39, GROUP_NA_C),
    "MX-MONTERREY-1": ("mx-central-monterrey", "MX", 25.69, -100.31, GROUP_NA_C),
    "SA-SANTIAGO-1": ("sa-west-santiago", "CL", -33.45, -70.66, GROUP_SA),
    "SA-VALPARAISO-1": ("sa-west-valparaiso", "CL", -33.04, -71.62, GROUP_SA),
    "SA-SAOPAULO-1": ("sa-east-saopaulo", "BR", -23.55, -46.63, GROUP_SA),
    "SA-VINHEDO-1": ("sa-east-vinhedo", "BR", -23.03, -46.97, GROUP_SA),
    "SA-BOGOTA-1": ("sa-north-bogota", "CO", 4.71, -74.07, GROUP_SA),
    "UK-LONDON-1": ("eu-west-london", "GB", 51.51, -0.13, GROUP_EU_W),
    "UK-CARDIFF-1": ("eu-west-cardiff", "GB", 51.48, -3.18, GROUP_EU_W),
    "EU-AMSTERDAM-1": ("eu-west-amsterdam", "NL", 52.37, 4.90, GROUP_EU_W),
    "EU-FRANKFURT-1": ("eu-central-frankfurt", "DE", 50.11, 8.68, GROUP_EU_C),
    "EU-PARIS-1": ("eu-west-paris", "FR", 48.86, 2.35, GROUP_EU_W),
    "EU-MARSEILLE-1": ("eu-south-marseille", "FR", 43.30, 5.37, GROUP_EU_S),
    "EU-MILAN-1": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "EU-MADRID-1": ("eu-south-madrid", "ES", 40.42, -3.70, GROUP_EU_S),
    "EU-STOCKHOLM-1": ("eu-north-stockholm", "SE", 59.33, 18.07, GROUP_EU_N),
    "EU-ZURICH-1": ("eu-central-zurich", "CH", 47.37, 8.55, GROUP_EU_C),
    "EU-JOVANOVAC-1": ("eu-central-serbia", "RS", 44.02, 21.01, GROUP_EU_C),
    "ME-DUBAI-1": ("me-central-dubai", "AE", 25.27, 55.31, GROUP_ME),
    "ME-ABUDHABI-1": ("me-central-abudhabi", "AE", 24.47, 54.37, GROUP_ME),
    "ME-RIYADH-1": ("me-central-riyadh", "SA", 24.71, 46.68, GROUP_ME),
    "ME-JEDDAH-1": ("me-west-jeddah", "SA", 21.49, 39.19, GROUP_ME),
    "ME-DCC-DOHA-1": ("me-central-doha", "QA", 25.35, 51.18, GROUP_ME),
    "IL-JERUSALEM-1": ("me-west-jerusalem", "IL", 31.78, 35.22, GROUP_ME),
    "AF-JOHANNESBURG-1": ("af-south-johannesburg", "ZA", -26.20, 28.05, GROUP_AF),
    "AP-MUMBAI-1": ("ap-south-mumbai", "IN", 19.08, 72.88, GROUP_AP_S),
    "AP-HYDERABAD-1": ("ap-south-hyderabad", "IN", 17.39, 78.49, GROUP_AP_S),
    "AP-DELHI-1": ("ap-south-delhi", "IN", 28.61, 77.21, GROUP_AP_S),
    "AP-CHUNCHEON-1": ("ap-northeast-chuncheon", "KR", 37.88, 127.73, GROUP_AP_E),
    "AP-SEOUL-1": ("ap-northeast-seoul", "KR", 37.57, 126.98, GROUP_AP_E),
    "AP-OSAKA-1": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "AP-TOKYO-1": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "AP-SINGAPORE-1": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "AP-SINGAPORE-2": ("ap-southeast-singapore", "SG", 1.35, 103.82, GROUP_AP_SE),
    "AP-MELBOURNE-1": ("ap-southeast-melbourne", "AU", -37.81, 144.96, GROUP_AP_SE),
    "AP-SYDNEY-1": ("ap-southeast-sydney", "AU", -33.87, 151.21, GROUP_AP_SE),
    "AP-IBARAKI-1": ("ap-northeast-ibaraki", "JP", 36.34, 140.45, GROUP_AP_E),
    "AP-DCC-CANBERRA-1": ("ap-southeast-canberra", "AU", -35.28, 149.13, GROUP_AP_SE),
    "AP-BATAM-1": ("ap-southeast-batam", "ID", 1.13, 104.05, GROUP_AP_SE),
    "AP-KULAI-2": ("ap-southeast-kulai", "MY", 1.66, 103.61, GROUP_AP_SE),
    "AP-DCC-OSAKA-1": ("ap-northeast-osaka", "JP", 34.69, 135.50, GROUP_AP_E),
    "AP-DCC-TOKYO-1": ("ap-northeast-tokyo", "JP", 35.68, 139.76, GROUP_AP_E),
    "AF-CASABLANCA-1": ("af-north-casablanca", "MA", 33.57, -7.59, GROUP_AF),
    "EU-DCC-DUBLIN-1": ("eu-west-dublin", "IE", 53.35, -6.26, GROUP_EU_W),
    "EU-DCC-DUBLIN-2": ("eu-west-dublin", "IE", 53.35, -6.26, GROUP_EU_W),
    "EU-DCC-MILAN-1": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "EU-DCC-MILAN-2": ("eu-south-milan", "IT", 45.46, 9.19, GROUP_EU_S),
    "EU-DCC-RATING-1": ("eu-central-rating", "DE", 51.30, 6.85, GROUP_EU_C),
    "EU-DCC-RATING-2": ("eu-central-rating", "DE", 51.30, 6.85, GROUP_EU_C),
    "EU-DCC-ZURICH-1": ("eu-central-zurich", "CH", 47.37, 8.55, GROUP_EU_C),
    "EU-MADRID-3": ("eu-south-madrid", "ES", 40.42, -3.70, GROUP_EU_S),
    "EU-TURIN-1": ("eu-south-turin", "IT", 45.07, 7.69, GROUP_EU_S),
}


# ---- Per-provider lookup tables ---------------------------------------------
PER_PROVIDER = {
    "aws": AWS,
    "gcp": GCP,
    "azure": AZURE,
    "oci": OCI,
    "vultr": VULTR,
    "lambdalabs": LAMBDA,
    "nebius": NEBIUS,
    "verda": VERDA,
}


# ---- AWS Local Zone / Wavelength: derive from the parent region prefix ----
def _aws_special_region(raw: str) -> Optional[tuple]:
    """Map AWS Local Zones (us-east-1-nyc-1) and Wavelength (eu-west-3-wl1-*)
    back to their parent canonical region with a `-zone` group suffix."""
    parts = raw.split("-")
    # Try increasingly shorter prefixes until we find a real AWS region.
    for length in (4, 3):
        if len(parts) > length:
            parent = "-".join(parts[:length])
            if parent in AWS:
                canonical, country, lat, lon, group = AWS[parent]
                return (f"{canonical}-zone", country, lat, lon, group)
    return None


def _strip_gcp_zone(raw: str) -> Optional[str]:
    """asia-east1-a -> asia-east1, africa-south1-c -> africa-south1."""
    if len(raw) > 2 and raw[-2] == "-" and raw[-1].isalpha():
        return raw[:-2]
    return None


def _country_code_from_segment(raw: str) -> Optional[str]:
    """Extract a 2-letter ISO country code from common embedded patterns.

    Examples:
        AP-JP-1     -> JP
        EU-CZ-1     -> CZ
        EUR-IS-2    -> IS  (the second 2-letter chunk wins)
        eu-west-uk-lo-1 -> UK -> GB (alias resolved upstream by COUNTRY)
        ba-bosniaandherzegovina -> BA
    """
    parts = [p for p in raw.upper().split("-") if p]
    candidates = []
    for p in parts:
        if len(p) == 2 and p.isalpha():
            candidates.append(p)
    # Prefer codes that map cleanly to a known country.
    for code in candidates:
        if code in COUNTRY:
            return code
    return candidates[0] if candidates else None


def lookup(provider: str, raw_region: str) -> Optional[tuple]:
    """Return (canonical, country, lat, lon, group) or None if unmapped."""
    if not raw_region:
        return None

    # Direct provider table hit (handles AWS/GCP/Azure/OCI/Vultr/Lambda/Nebius).
    table = PER_PROVIDER.get(provider)
    if table:
        if raw_region in table:
            return table[raw_region]
        # Case-insensitive retry for OCI (we've seen lowercased variants).
        upper = raw_region.upper()
        if upper in table:
            return table[upper]
        lower = raw_region.lower()
        if lower in table:
            return table[lower]

    # GCP zone-suffix fallback: asia-east1-a -> asia-east1.
    if provider == "gcp":
        parent = _strip_gcp_zone(raw_region)
        if parent and parent in GCP:
            canonical, country, lat, lon, group = GCP[parent]
            return (canonical, country, lat, lon, group)

    # AWS Local Zones / Wavelength fallback.
    if provider == "aws":
        special = _aws_special_region(raw_region)
        if special:
            return special

    # Marketplace / structured-name fallback: try to extract an ISO-2
    # country code from the raw string.
    code = _country_code_from_segment(raw_region)
    if code and code in COUNTRY:
        country, lat, lon, group = COUNTRY[code]
        return (None, country, lat, lon, group)

    return None


# ---- I/O --------------------------------------------------------------------

def discover_pairs(src: str) -> list[tuple[str, str]]:
    """Discover distinct (provider, raw_region) pairs from the source."""
    con = duckdb.connect()
    if src.endswith(".db"):
        con.execute(f"ATTACH '{src}' AS src (READ_ONLY)")
        rows = con.execute(
            "SELECT DISTINCT provider, region FROM src.gpu_prices "
            "ORDER BY provider, region"
        ).fetchall()
    else:
        glob = f"{src}/**/*.parquet"
        rows = con.execute(
            f"SELECT DISTINCT provider, region "
            f"FROM read_parquet('{glob}', hive_partitioning = true) "
            f"ORDER BY provider, region"
        ).fetchall()
    return rows


def read_existing(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    out = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            out[(r["provider"], r["raw_region"])] = r
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/parquet/prices",
                    help="Parquet root or path to a SQLite DB")
    ap.add_argument("--out", default="data/regions.csv",
                    help="Output CSV path")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_existing(out_path)
    pairs = discover_pairs(args.src)
    print(f"Discovered {len(pairs)} (provider, raw_region) pairs")

    rows = []
    for provider, raw_region in pairs:
        key = (provider, raw_region)
        if key in existing:
            # Hand-edited rows win.
            rows.append(existing[key])
            continue

        looked = lookup(provider, raw_region)
        if looked:
            canonical, country, lat, lon, group = looked
            rows.append({
                "provider": provider,
                "raw_region": raw_region,
                "region_canonical": canonical or "",
                "country": country or "",
                "lat": f"{lat:.4f}" if lat is not None else "",
                "lon": f"{lon:.4f}" if lon is not None else "",
                "region_group": group or "",
            })
        else:
            rows.append({
                "provider": provider,
                "raw_region": raw_region,
                "region_canonical": "",
                "country": "",
                "lat": "",
                "lon": "",
                "region_group": "",
            })

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    mapped = sum(1 for r in rows if r["region_group"])
    print(f"Wrote {len(rows)} rows -> {out_path}  ({mapped} mapped, {len(rows) - mapped} unmapped)")
    if mapped < len(rows):
        print("\nUnmapped sample:")
        for r in rows:
            if not r["region_group"]:
                print(f"  {r['provider']:>12} | {r['raw_region']}")
                if rows.index(r) > 30:
                    break


if __name__ == "__main__":
    sys.exit(main())
