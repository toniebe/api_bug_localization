import os
import re

def clean_name_no_separator(x: str) -> str:
    """
    Bersihkan nama supaya aman untuk folder:
    - Hapus semua karakter non alphanumeric
    - Tidak memakai underscore atau separator lain
    """
    # hilangkan semua karakter selain huruf / angka
    x = re.sub(r"[^A-Za-z0-9]+", "", x)
    return x


def get_ltr_model_path(org: str, project: str) -> str:
    """
    Return path:
      models/{OrgName}{ProjectName}/dev_recommender_ltr.json
    """
    folder = f"models/{clean_name_no_separator(org)}{clean_name_no_separator(project)}"
    os.makedirs(folder, exist_ok=True)
    return f"{folder}/dev_recommender_ltr.json"


def get_ltr_dataset_path(org: str, project: str) -> str:
    """
    Return path:
      data/{OrgName}{ProjectName}/ltr_training_dataset.csv
    """
    folder = f"data/{clean_name_no_separator(org)}{clean_name_no_separator(project)}"
    os.makedirs(folder, exist_ok=True)
    return f"{folder}/ltr_training_dataset.csv"
