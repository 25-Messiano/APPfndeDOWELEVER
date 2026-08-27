from core.downloader import baixar_fnde

if __name__ == "__main__":
    r = baixar_fnde("2902708", "Araci", "BA", 2025, "14.232.086/0001-92")
    print(r)
