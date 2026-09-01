import flet as ft
import threading
import json
import os
import time
from datetime import datetime
import requests # <== SUNTIKAN BARU UNTUK JALUR CLOUDFLARE

# Mencoba memuat modul database
try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


    
# ==========================================
# VARIABEL CACHE GLOBAL & FILTER
# ==========================================
sekarang = datetime.now()
tgl_hari_ini = sekarang.strftime("%Y-%m-%d")

GLOBAL_DATA = {
    "db_status": "Menghubungkan...",
    "db_color": "#F39C12", 
    "tgl_awal": tgl_hari_ini,
    "tgl_akhir": tgl_hari_ini,
    "filter_cari": "",
    "kas_masuk": 0, "kas_keluar": 0, "sisa_saldo": 0,
    "bahan_baku": {}, "produksi": {}, "top_5": [], "tren_7_hari": [], # <== TAMBAHAN BARU
    "bahan_baku": {}, "produksi": {}, "top_5": [],
    "trx_live": [], "trx_dibayar": [], "trx_beli": [], "trx_kirim": [],
    "mst_suplier": [], "mst_customer": [], "mst_harga": [],
    "list_komoditas": [], # <== TAMBAHKAN BARIS INI
    "antrean": [], "chat_history": []
}

ACTIVE_UI = {}
DB_LOCK = threading.Lock() 

# ==========================================
# PROGRAM UTAMA APLIKASI
# ==========================================
def main(page: ft.Page):
    page.title = "NMC Executive"
    page.bgcolor = "#0A1128" 
    page.window.width = 400
    page.window.height = 750
    page.padding = 0 
    page.theme_mode = ft.ThemeMode.DARK 

    # ==========================================
    # MESIN PENYIMPANAN HYBRID (ANTI-RESET ANDROID)
    # ==========================================
    FILE_CONFIG = "nmc_mobile_config.json"

    def muat_pengaturan():
        # 1. Tuliskan semua nilai bawaan wajib (Default) di sini
        bawaan = {
            "host": "192.168.10.38", 
            "port": "3306", 
            "user": "root", 
            "password": "", 
            "cf_url": "", 
            "refresh_interval": "3", 
            "overtime_limit": "2.0"
        }
        
        dimuat = {}
        
        # 2. Coba baca dari memori internal Android (SharedPreferences)
        try:
            if hasattr(page, "client_storage") and page.client_storage.contains_key("nmc_config"):
                dimuat = json.loads(page.client_storage.get("nmc_config"))
        except: pass

        # 3. Jika gagal, coba baca dari file lokal (Untuk Uji Coba Laptop)
        if not dimuat:
            try:
                if os.path.exists(FILE_CONFIG):
                    with open(FILE_CONFIG, "r") as f:
                        dimuat = json.load(f)
            except: pass

        # 4. GABUNGKAN (Update) nilai bawaan dengan data yang dimuat
        # Ini mengamankan agar jika ada parameter baru, datanya tidak menjadi kosong/error
        bawaan.update(dimuat)
        return bawaan

    def simpan_pengaturan(data):
        # 1. Simpan ke memori internal Android secara permanen
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.set("nmc_config", json.dumps(data))
        except: pass

        # 2. Simpan ke file lokal (sebagai cadangan di Laptop)
        try:
            with open(FILE_CONFIG, "w") as f:
                json.dump(data, f)
        except: pass

    db_config = muat_pengaturan()
    halaman_aktif = "welcome"
    sub_halaman_aktif = ""


    # ==========================================
    # TOMBOL CHAT INTERNAL MENGAMBANG (FAB) DITUTUP PERMANEN
    # ==========================================
    page.floating_action_button = ft.FloatingActionButton(content=ft.Text("💬"), on_click=lambda e: None)
    page.floating_action_button.visible = False


    # ========================================================
    # SUNTIKAN BARU: MESIN CRUD MASTER DATA (POP-UP FORM)
    # ========================================================
    form_mode_aktif = {"tabel": "", "aksi": ""} 

    # --- INPUT FORM SUPPLIER ---
    f_sup_kode = ft.TextField(label="Kode Relasi", disabled=True, bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_sup_nama = ft.TextField(label="Nama Lengkap", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_sup_tipe = ft.Dropdown(label="Tipe Relasi", options=[ft.dropdown.Option(x) for x in ["Umum", "Petani Mandiri", "Pengepul / RAM", "Koperasi / Plasma", "Pabrik Pembeli PKS"]], bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_sup_kontak = ft.TextField(label="No. Telepon", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_sup_status = ft.Dropdown(label="Status", options=[ft.dropdown.Option("Aktif"), ft.dropdown.Option("Non-Aktif")], bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)

    # --- INPUT FORM HARGA ---
    f_hrg_kode = ft.TextField(label="Kode Harga", disabled=True, bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_tgl = ft.TextField(label="Tgl Berlaku (YYYY-MM-DD)", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_komoditas = ft.Dropdown(label="Pilih Komoditas", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_tipe = ft.Dropdown(label="Kategori Relasi", options=[ft.dropdown.Option(x) for x in ["Umum", "Petani Mandiri", "Pengepul / RAM", "Koperasi / Plasma", "Pabrik Pembeli PKS"]], bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_sup = ft.TextField(label="Nama Supplier", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_nom = ft.TextField(label="Harga / Kg (Rp)", bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)
    f_hrg_status = ft.Dropdown(label="Status", options=[ft.dropdown.Option("Aktif"), ft.dropdown.Option("Non-Aktif")], bgcolor="#0A1128", border_color="#3498DB", color="white", text_size=12)

    lbl_form_status = ft.Text("", size=11, weight="bold")

    def eksekusi_simpan_master(e):
        tabel, aksi = form_mode_aktif["tabel"], form_mode_aktif["aksi"]
        lbl_form_status.value = "⏳ Menyimpan data..."
        lbl_form_status.color = "#F1C40F"
        page.update()
        
        cf_url = db_config.get("cf_url", "").strip()
        
        # Rakit data yang mau dikirim
        payload = {"tabel": tabel, "aksi": aksi, "data": {}}
        if tabel == "supplier":
            payload["data"] = {"kode": f_sup_kode.value, "nama": f_sup_nama.value, "tipe": f_sup_tipe.value, "kontak": f_sup_kontak.value, "status": f_sup_status.value}
        else:
            payload["data"] = {"kode": f_hrg_kode.value, "tanggal": f_hrg_tgl.value, "komoditas": f_hrg_komoditas.value, "tipe_supplier": f_hrg_tipe.value, "nama_supplier": f_hrg_sup.value, "nominal": float(f_hrg_nom.value.replace(",", "")), "status": f_hrg_status.value}

        try:
            # --- JALUR CLOUDFLARE (JARAK JAUH) ---
            if cf_url != "":
                url_target = cf_url.rstrip("/") + "/api/master_crud"
                r = requests.post(url_target, json={"operasi": "simpan", **payload}, timeout=10)
                r.raise_for_status()
            
            # --- JALUR LOKAL (WIFI PABRIK) ---
            else:
                if not HAS_MYSQL: return
                conn = mysql.connector.connect(host=db_config["host"], port=int(db_config["port"]), user=db_config["user"], password=db_config["password"], database="db_timbangan")
                cursor = conn.cursor()
                d = payload["data"]
                
                if tabel == "supplier":
                    if aksi == "tambah":
                        cursor.execute("SELECT kode FROM master_supplier WHERE kode LIKE 'SUP-%' ORDER BY kode DESC LIMIT 1")
                        last = cursor.fetchone()
                        new_kode = f"SUP-{int(last[0].split('-')[1]) + 1:03d}" if last else "SUP-001"
                        cursor.execute("INSERT INTO master_supplier (kode, nama, tipe, kontak, alamat, status) VALUES (%s, %s, %s, %s, '-', %s)", (new_kode, d["nama"], d["tipe"], d["kontak"], d["status"]))
                    else:
                        cursor.execute("UPDATE master_supplier SET nama=%s, tipe=%s, kontak=%s, status=%s WHERE kode=%s", (d["nama"], d["tipe"], d["kontak"], d["status"], d["kode"]))
                elif tabel == "harga":
                    if aksi == "tambah":
                        cursor.execute("SELECT kode FROM master_harga WHERE kode LIKE 'HRG-%' ORDER BY kode DESC LIMIT 1")
                        last = cursor.fetchone()
                        new_kode = f"HRG-{int(last[0].split('-')[1]) + 1:03d}" if last else "HRG-001"
                        cursor.execute("UPDATE master_harga SET status='Non-Aktif' WHERE tipe_supplier=%s AND IFNULL(nama_supplier, '')=%s AND komoditas=%s", (d["tipe_supplier"], d["nama_supplier"], d["komoditas"]))
                        cursor.execute("INSERT INTO master_harga (kode, tanggal, komoditas, tipe_supplier, nama_supplier, nominal, status) VALUES (%s, %s, %s, %s, %s, %s, %s)", (new_kode, d["tanggal"], d["komoditas"], d["tipe_supplier"], d["nama_supplier"], d["nominal"], d["status"]))
                    else:
                        cursor.execute("UPDATE master_harga SET tanggal=%s, komoditas=%s, tipe_supplier=%s, nama_supplier=%s, nominal=%s, status=%s WHERE kode=%s", (d["tanggal"], d["komoditas"], d["tipe_supplier"], d["nama_supplier"], d["nominal"], d["status"], d["kode"]))
                conn.commit()
                conn.close()

            # 1. TUTUP POP-UP TERLEBIH DAHULU AGAR INSTAN
            dlg_master.open = False
            page.snack_bar = ft.SnackBar(ft.Text(f"✅ Data {tabel} berhasil {aksi}!"), bgcolor="#27AE60")
            page.snack_bar.open = True
            page.update() 
            
            # 2. BARU REFRESH DATA DI BACKGROUND
            tarik_data_database()
            update_live_ui()
            
        except Exception as ex:
            lbl_form_status.value = f"❌ Error: {ex}"
            lbl_form_status.color = "#E74C3C"
            page.update()

    def eksekusi_hapus_master(e):
        tabel = form_mode_aktif["tabel"]
        kode = f_sup_kode.value if tabel == "supplier" else f_hrg_kode.value
        cf_url = db_config.get("cf_url", "").strip()
        
        lbl_form_status.value = "⏳ Menghapus data..."
        lbl_form_status.color = "#E74C3C"
        page.update()
        
        try:
            # --- JALUR CLOUDFLARE ---
            if cf_url != "":
                url_target = cf_url.rstrip("/") + "/api/master_crud"
                r = requests.post(url_target, json={"operasi": "hapus", "tabel": tabel, "kode": kode}, timeout=10)
                r.raise_for_status()
            
            # --- JALUR LOKAL ---
            else:
                if not HAS_MYSQL: return
                conn = mysql.connector.connect(host=db_config["host"], port=int(db_config["port"]), user=db_config["user"], password=db_config["password"], database="db_timbangan")
                cursor = conn.cursor()
                if tabel == "supplier": cursor.execute("DELETE FROM master_supplier WHERE kode=%s", (kode,))
                else: cursor.execute("DELETE FROM master_harga WHERE kode=%s", (kode,))
                conn.commit()
                conn.close()

            # 1. TUTUP POP-UP TERLEBIH DAHULU AGAR INSTAN
            dlg_master.open = False
            page.snack_bar = ft.SnackBar(ft.Text(f"🗑️ Data dihapus!"), bgcolor="#E74C3C")
            page.snack_bar.open = True
            page.update()
            
            # 2. BARU REFRESH DATA DI BACKGROUND
            tarik_data_database()
            update_live_ui()
            
        except Exception as ex:
            lbl_form_status.value = f"❌ Error: {ex}"
            page.update()

    # ========================================================
    # REVISI: FUNGSI TUTUP DIALOG YANG AMAN
    # ========================================================
    def tutup_dialog_master(e=None):
        dlg_master.open = False
        page.update()

    btn_simpan_m = ft.Container(content=ft.Text("Simpan", color="white", weight="bold"), bgcolor="#27AE60", padding=10, border_radius=5, ink=True, on_click=eksekusi_simpan_master)
    btn_hapus_m = ft.Container(content=ft.Text("Hapus", color="white", weight="bold"), bgcolor="#C0392B", padding=10, border_radius=5, ink=True, on_click=eksekusi_hapus_master)
    
    # Gunakan fungsi penutup yang rapi di sini
    btn_batal_m = ft.Container(content=ft.Text("Batal", color="white", weight="bold"), bgcolor="#7F8C8D", padding=10, border_radius=5, ink=True, on_click=tutup_dialog_master)

    konten_dialog = ft.Column([], tight=True, scroll="auto", spacing=5)
    dlg_master = ft.AlertDialog(title=ft.Text("Master Data", size=16, weight="bold"), content=ft.Container(width=320, content=konten_dialog), actions=[btn_hapus_m, btn_batal_m, btn_simpan_m], actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN, bgcolor="#141A29")

    def buka_form_master(tabel, aksi, data_baris=None):
        form_mode_aktif["tabel"] = tabel
        form_mode_aktif["aksi"] = aksi
        lbl_form_status.value = ""
        konten_dialog.controls.clear()
        btn_hapus_m.visible = (aksi == "edit")

        if tabel == "supplier":
            dlg_master.title.value = "Tambah Supplier" if aksi == "tambah" else "Edit Supplier"
            konten_dialog.controls.extend([f_sup_kode, f_sup_nama, f_sup_tipe, f_sup_kontak, f_sup_status, lbl_form_status])
            
            if aksi == "tambah":
                f_sup_kode.value, f_sup_nama.value, f_sup_tipe.value, f_sup_kontak.value, f_sup_status.value = "[Otomatis]", "", "Petani Mandiri", "", "Aktif"
            elif aksi == "edit":
                # KITA AMBIL LANGSUNG DARI MEMORI HP, TANPA LOADING DATABASE!
                f_sup_kode.value = data_baris[0]
                f_sup_nama.value = data_baris[1]
                f_sup_tipe.value = data_baris[2]
                f_sup_kontak.value = data_baris[3]
                f_sup_status.value = data_baris[4]
                
        elif tabel == "harga":
            dlg_master.title.value = "Tambah Harga" if aksi == "tambah" else "Edit Harga"
            opsi_komoditas = ["Semua Barang"] + GLOBAL_DATA.get("list_komoditas", [])
            f_hrg_komoditas.options = [ft.dropdown.Option(x) for x in opsi_komoditas]
            konten_dialog.controls.extend([f_hrg_kode, f_hrg_tgl, f_hrg_komoditas, f_hrg_tipe, f_hrg_sup, f_hrg_nom, f_hrg_status, lbl_form_status])
            
            if aksi == "tambah":
                f_hrg_kode.value, f_hrg_tgl.value, f_hrg_komoditas.value, f_hrg_tipe.value, f_hrg_sup.value, f_hrg_nom.value, f_hrg_status.value = "[Otomatis]", datetime.now().strftime("%Y-%m-%d"), "Semua Barang", "Umum", "- Berlaku Semua -", "0", "Aktif"
            elif aksi == "edit":
                # KITA AMBIL LANGSUNG DARI MEMORI HP, TANPA LOADING DATABASE!
                f_hrg_kode.value = data_baris[0]
                f_hrg_tgl.value = data_baris[1]
                f_hrg_komoditas.value = data_baris[2]
                f_hrg_tipe.value = data_baris[3]
                f_hrg_sup.value = data_baris[4]
                f_hrg_nom.value = str(int(float(data_baris[5])))
                f_hrg_status.value = data_baris[6]

        if dlg_master not in page.overlay:
            page.overlay.append(dlg_master)
            
        dlg_master.open = True
        page.update()
    # ========================================================

    # ==========================================
    # MESIN INJEKSI UI (UPDATE TANPA REFRESH)
    # ==========================================
    def update_live_ui():
        if halaman_aktif not in ["dashboard", "transaksi", "antrean", "pengaturan", "chat"]: return

        if "ind_warna" in ACTIVE_UI:
            ACTIVE_UI["ind_warna"].bgcolor = GLOBAL_DATA["db_color"]

        # --- UPDATE DASHBOARD ---
        if halaman_aktif == "dashboard" and "txt_kas_masuk" in ACTIVE_UI:
            
            # --- RENDER GRAFIK TREN 7 HARI (VERSI PROFESIONAL + KALENDER PENUH) ---
            if "list_tren" in ACTIVE_UI:
                ACTIVE_UI["list_tren"].controls.clear()
                if GLOBAL_DATA["db_status"] == "Konek DB":
                    from datetime import timedelta # Suntikan lokal untuk memutar waktu
                    
                    # 1. GENERATOR KALENDER: Menciptakan paksa daftar 7 hari terakhir
                    tgl_skrg = datetime.now()
                    list_7_hari = [(tgl_skrg - timedelta(days=i)).strftime("%m-%d") for i in range(6, -1, -1)]
                    
                    # 2. Mengubah format data dari DB agar mudah dicocokkan dengan kalender
                    data_db = {}
                    if GLOBAL_DATA["tren_7_hari"]:
                        for r in GLOBAL_DATA["tren_7_hari"]:
                            data_db[str(r[0])] = (float(r[1]), float(r[2]))
                            
                    # 3. Mencari nilai tertinggi untuk tinggi frame maksimal
                    max_val = 1
                    for masuk, keluar in data_db.values():
                        if masuk > max_val: max_val = masuk
                        if keluar > max_val: max_val = keluar
                        
                    # Spacing dirapatkan menjadi 10 agar pas menampung 7 pilar batang di layar HP
                    chart_row = ft.Row(alignment="center", spacing=10, vertical_alignment="end")
                    
                    def format_angka_k(val):
                        if val == 0: return ""
                        if val >= 1000: return f"{val/1000:.1f}K".replace(".0K", "K")
                        return f"{val:.0f}"
                    
                    # 4. Menggambar 7 Pilar secara paksa (Meskipun datanya 0)
                    for tgl in list_7_hari:
                        masuk, keluar = data_db.get(tgl, (0.0, 0.0))
                        
                        MAX_H = 45 
                        h_masuk = (masuk / max_val) * MAX_H if masuk > 0 else 0
                        h_keluar = (keluar / max_val) * MAX_H if keluar > 0 else 0
                        
                        txt_masuk = ft.Text(format_angka_k(masuk), size=7, color="#3498DB", weight="bold")
                        bar_masuk = ft.Container(width=10, height=h_masuk if h_masuk > 2 else (2 if masuk > 0 else 0), bgcolor="#3498DB", border_radius=2, tooltip=f"Masuk: {masuk:,.0f} Kg")
                        col_masuk = ft.Column([txt_masuk, bar_masuk], alignment="end", spacing=2, horizontal_alignment="center")
                        
                        txt_keluar = ft.Text(format_angka_k(keluar), size=7, color="#E74C3C", weight="bold")
                        bar_keluar = ft.Container(width=10, height=h_keluar if h_keluar > 2 else (2 if keluar > 0 else 0), bgcolor="#E74C3C", border_radius=2, tooltip=f"Keluar: {keluar:,.0f} Kg")
                        col_keluar = ft.Column([txt_keluar, bar_keluar], alignment="end", spacing=2, horizontal_alignment="center")
                        
                        group_bar = ft.Column([
                            ft.Column([
                                ft.Row([col_masuk, col_keluar], spacing=2, vertical_alignment="end")
                            ], height=60, alignment="end"), 
                            ft.Text(tgl, size=8, color="#BDC3C7", text_align="center")
                        ], spacing=5, horizontal_alignment="center")
                        
                        chart_row.controls.append(group_bar)
                    
                    grid_bg = ft.Column([
                        ft.Container(height=1, bgcolor="#2C3E50"),
                        ft.Container(height=18),
                        ft.Container(height=1, bgcolor="#2C3E50"),
                        ft.Container(height=18),
                        ft.Container(height=1, bgcolor="#2C3E50"),
                    ], spacing=0)
                    
                    area_grafik = ft.Stack([
                        ft.Container(content=grid_bg, padding=12), 
                        chart_row
                    ])
                    
                    legenda = ft.Row([
                        ft.Container(width=10, height=10, bgcolor="#3498DB", border_radius=5), ft.Text("Masuk (Beli)", size=9, color="#BDC3C7"), ft.Container(width=10),
                        ft.Container(width=10, height=10, bgcolor="#E74C3C", border_radius=5), ft.Text("Keluar (Jual)", size=9, color="#BDC3C7")
                    ], alignment="center")
                    
                    ACTIVE_UI["list_tren"].controls.append(legenda)
                    ACTIVE_UI["list_tren"].controls.append(ft.Container(content=area_grafik, padding=10))
                else:
                    ACTIVE_UI["list_tren"].controls.append(ft.Row([ft.Text("⚠️ Disconnect", color="#E74C3C", size=12, italic=True)], alignment="center"))

            ACTIVE_UI["txt_kas_masuk"].value = f"Rp {GLOBAL_DATA['kas_masuk']:,.0f}".replace(",", ".")
            ACTIVE_UI["txt_kas_keluar"].value = f"Rp {GLOBAL_DATA['kas_keluar']:,.0f}".replace(",", ".")
            ACTIVE_UI["txt_sisa_saldo"].value = f"Rp {GLOBAL_DATA['sisa_saldo']:,.0f}".replace(",", ".")

            ACTIVE_UI["list_bahan_baku"].controls.clear()
            if GLOBAL_DATA["db_status"] == "Konek DB":
                if GLOBAL_DATA["bahan_baku"]:
                    for nama, kg in GLOBAL_DATA["bahan_baku"].items():
                        ACTIVE_UI["list_bahan_baku"].controls.append(ft.Row([ft.Text(nama, color="#BDC3C7"), ft.Text(f"{kg:,.0f} Kg".replace(",", "."), color="white", weight="bold")], alignment="spaceBetween"))
                else:
                    ACTIVE_UI["list_bahan_baku"].controls.append(ft.Row([ft.Text("0 Kg", color="white", weight="bold")], alignment="center"))
            else:
                ACTIVE_UI["list_bahan_baku"].controls.append(ft.Row([ft.Text("⚠️ Disconnect", color="#E74C3C", weight="bold", size=12)], alignment="center"))

            # -----------------------------------------------------
            # UPDATE PROPORSI PRODUKSI (GRAFIK BALOK AMAN TAHAN BANTING)
            # -----------------------------------------------------
            if "list_produksi" in ACTIVE_UI:
                ACTIVE_UI["list_produksi"].controls.clear()
                if GLOBAL_DATA["db_status"] == "Konek DB":
                    warna_palet = ["#3498DB", "#2ECC71", "#E67E22", "#9B59B6", "#1ABC9C"]
                    if GLOBAL_DATA["produksi"]:
                        total_produksi = sum(GLOBAL_DATA["produksi"].values())
                        
                        for i, (nama, kg) in enumerate(GLOBAL_DATA["produksi"].items()):
                            w = warna_palet[i % len(warna_palet)]
                            persen = (kg / total_produksi * 100) if total_produksi > 0 else 0
                            
                            baris_teks = ft.Row([
                                ft.Row([
                                    ft.Container(width=10, height=10, border_radius=5, bgcolor=w), 
                                    ft.Text(str(nama)[:20], color="#BDC3C7", size=12)
                                ], spacing=8), 
                                ft.Row([
                                    ft.Text(f"{persen:.1f}%", color=w, size=11, weight="bold"),
                                    ft.Text(f"{kg:,.0f} Kg".replace(",", "."), color="white", weight="bold", size=12)
                                ], spacing=10)
                            ], alignment="spaceBetween")
                            
                            baris_visual = ft.ProgressBar(value=persen/100, color=w, bgcolor="#2C3E50", height=6)
                            
                            ACTIVE_UI["list_produksi"].controls.append(ft.Column([baris_teks, baris_visual], spacing=5))
                            ACTIVE_UI["list_produksi"].controls.append(ft.Container(height=5))
                    else:
                        ACTIVE_UI["list_produksi"].controls.append(ft.Row([ft.Text("0 Kg", color="white", weight="bold")], alignment="center"))
                else:
                    ACTIVE_UI["list_produksi"].controls.append(ft.Row([ft.Text("⚠️ Disconnect", color="#E74C3C", weight="bold", size=12)], alignment="center"))

            ACTIVE_UI["list_top5"].controls.clear()
            if GLOBAL_DATA["db_status"] == "Konek DB":
                if GLOBAL_DATA["top_5"]:
                    for i, r in enumerate(GLOBAL_DATA["top_5"]):
                        nm = r[0] if r[0] else "Tanpa Nama"
                        kg = f"{float(r[1]):,.0f} Kg".replace(",", ".")
                        ACTIVE_UI["list_top5"].controls.append(ft.Row([ft.Text(f"{i+1}. {nm[:20]}", color="#BDC3C7", size=12), ft.Text(kg, color="white", weight="bold", size=12)], alignment="spaceBetween"))
                else:
                    ACTIVE_UI["list_top5"].controls.append(ft.Row([ft.Text("Data Kosong", color="gray", size=12)], alignment="center"))
            else:
                ACTIVE_UI["list_top5"].controls.append(ft.Row([ft.Text("⚠️ Disconnect", color="#E74C3C", size=12, italic=True)], alignment="center"))

        # --- UPDATE TRANSAKSI ---
        if halaman_aktif == "transaksi" and "list_transaksi" in ACTIVE_UI:
            sub = sub_halaman_aktif if sub_halaman_aktif else "tiket"

            ACTIVE_UI["list_transaksi"].controls.clear()

            if GLOBAL_DATA["db_status"] == "Konek DB":
                data_render = []
                if sub == "tiket": data_render = GLOBAL_DATA["trx_live"]
                elif sub == "pembayaran": data_render = GLOBAL_DATA["trx_dibayar"]
                elif sub == "lap_beli": data_render = GLOBAL_DATA["trx_beli"]
                elif sub == "lap_kirim": data_render = GLOBAL_DATA["trx_kirim"]
                elif sub == "suplier": data_render = GLOBAL_DATA["mst_suplier"] + GLOBAL_DATA["mst_customer"]
                elif sub == "harga": data_render = GLOBAL_DATA["mst_harga"]

                if data_render:
                    for row in data_render:
                        if sub == "tiket":
                            warna_status = "#2ECC71" if "Lunas" in str(row[3]) else "#E74C3C"
                            ACTIVE_UI["list_transaksi"].controls.append(
                                ft.Container(bgcolor="#141a29", padding=15, border_radius=10, margin=10,
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"🎫 {row[0]}", weight="bold", color="white", size=14), ft.Text(str(row[3]), color=warna_status, size=11, weight="bold")], alignment="spaceBetween"),
                                        ft.Text(f"Supplier: {row[5]} | Supir: {row[4]}", color="#BDC3C7", size=11),
                                        ft.Row([ft.Text(f"Nopol: {row[1]}", color="#BDC3C7", size=11), ft.Text(f"{float(row[2]):,.0f} Kg".replace(",", "."), color="#3498DB", size=12, weight="bold")], alignment="spaceBetween")
                                    ])
                                )
                            )
                        elif sub == "pembayaran":
                            ACTIVE_UI["list_transaksi"].controls.append(
                                ft.Container(bgcolor="#0F2417", padding=15, border_radius=10, margin=10,
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"🧾 {row[0]}", weight="bold", color="white", size=12), ft.Text(f"{row[4]}", color="#BDC3C7", size=10)], alignment="spaceBetween"),
                                        ft.Text(f"Sup: {row[1]}", color="#F1C40F", size=11),
                                        ft.Row([ft.Text(f"Netto: {float(row[2]):,.0f} Kg".replace(",", "."), color="#BDC3C7", size=11), ft.Text(f"Rp {float(row[3]):,.0f}".replace(",", "."), color="#2ECC71", size=12, weight="bold")], alignment="spaceBetween")
                                    ])
                                )
                            )
                        elif sub == "lap_beli":
                            ACTIVE_UI["list_transaksi"].controls.append(
                                ft.Container(bgcolor="#141a29", padding=15, border_radius=10, margin=10,
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"📥 {row[0]}", weight="bold", color="white", size=12), ft.Text(f"{float(row[3]):,.0f} Kg".replace(",", "."), color="#3498DB", size=12, weight="bold")], alignment="spaceBetween"),
                                        ft.Text(f"Supplier: {row[4]} | Supir: {row[2]}", color="#BDC3C7", size=11),
                                        ft.Text(f"Plat: {row[1]}", color="#BDC3C7", size=11)
                                    ])
                                )
                            )
                        elif sub == "lap_kirim":
                            ACTIVE_UI["list_transaksi"].controls.append(
                                ft.Container(bgcolor="#141a29", padding=15, border_radius=10, margin=10,
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"📤 {row[0]}", weight="bold", color="white", size=12), ft.Text(f"{float(row[3]):,.0f} Kg".replace(",", "."), color="#3498DB", size=12, weight="bold")], alignment="spaceBetween"),
                                        ft.Text(f"Customer: {row[4]} | Supir: {row[2]}", color="#BDC3C7", size=11),
                                        ft.Text(f"Plat: {row[1]}", color="#BDC3C7", size=11)
                                    ])
                                )
                            )
                        elif sub == "suplier":
                            warna_tipe = "#9B59B6" if "Pabrik" in str(row[2]) else "#E67E22"
                            ACTIVE_UI["list_transaksi"].controls.append(
                                # Tambahkan event klik (on_click) di baris ini:
                                ft.Container(bgcolor="#141a29", padding=15, border_radius=10, margin=10, ink=True, on_click=lambda e, r=row: buka_form_master("supplier", "edit", r),
                                    content=ft.Row([
                                        ft.Text("👤", size=24), ft.Container(width=5),
                                        ft.Column([ft.Text(str(row[1])[:25], weight="bold", color="white", size=12), ft.Text(f"Kode: {row[0]}", color="#BDC3C7", size=10)]),
                                        ft.Container(expand=True), ft.Text(str(row[2]), color=warna_tipe, size=10, weight="bold")
                                    ])
                                )
                            )
                        elif sub == "harga":
                            ACTIVE_UI["list_transaksi"].controls.append(
                                ft.Container(bgcolor="#141a29", padding=15, border_radius=10, margin=10, ink=True, on_click=lambda e, r=row: buka_form_master("harga", "edit", r),
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"📦 {row[2]}", weight="bold", color="white", size=12), ft.Text(f"Rp {float(row[5]):,.0f}".replace(",", "."), color="#2ECC71", size=14, weight="bold")], alignment="spaceBetween"),
                                        ft.Row([ft.Text(f"Supplier: {row[4]}", color="#BDC3C7", size=11), ft.Text(f"Kode: {row[0]}", color="#BDC3C7", size=9)], alignment="spaceBetween")
                                    ])
                                )
                            )
                else:
                    ACTIVE_UI["list_transaksi"].controls.append(ft.Row([ft.Text("✅ Data tidak ditemukan.", color="#2ECC71", italic=True)], alignment="center"))
            else:
                ACTIVE_UI["list_transaksi"].controls.append(ft.Container(bgcolor="#311313", border_radius=8, padding=15, margin=10, content=ft.Row([ft.Text("⚠️", size=24), ft.Column([ft.Text("Disconnect dari Server", color="#E74C3C", size=14, weight="bold"), ft.Text("Periksa IP di Pengaturan.", color="#BDC3C7", size=11)])], spacing=15)))

        # --- UPDATE ANTREAN ---
        if halaman_aktif == "antrean" and "list_antrean" in ACTIVE_UI:
            ACTIVE_UI["list_antrean"].controls.clear()
            sub = sub_halaman_aktif if sub_halaman_aktif else "dalam_area"

            batas_overtime = float(db_config.get("overtime_limit", 2.0))

            if GLOBAL_DATA["db_status"] == "Konek DB":
                if GLOBAL_DATA["antrean"]:
                    waktu_skrg = datetime.now()
                    ada_data = False
                    
                    for row in GLOBAL_DATA["antrean"]:
                        jam_masuk_str = str(row[2])
                        try:
                            waktu_masuk = datetime.strptime(f"{waktu_skrg.strftime('%Y-%m-%d')} {jam_masuk_str}", "%Y-%m-%d %H:%M:%S")
                            selisih_jam = (waktu_skrg - waktu_masuk).total_seconds() / 3600
                        except: selisih_jam = 0

                        is_overtime = selisih_jam >= batas_overtime 
                        
                        if (sub == "dalam_area" and not is_overtime) or (sub == "overtime" and is_overtime):
                            ada_data = True
                            warna_bg = "#311313" if is_overtime else "#141a29"
                            teks_durasi = f"⏳ Durasi: {selisih_jam:.1f} Jam" if is_overtime else f"Masuk: {jam_masuk_str}"
                            warna_durasi = "#E74C3C" if is_overtime else "#F39C12"

                            ACTIVE_UI["list_antrean"].controls.append(
                                ft.Container(bgcolor=warna_bg, padding=15, border_radius=10, margin=10,
                                    content=ft.Column([
                                        ft.Row([ft.Text(f"🚚 Plat: {row[0]}", weight="bold", color="white", size=14), ft.Text(teks_durasi, color=warna_durasi, size=11, weight="bold")], alignment="spaceBetween"),
                                        ft.Text(f"Muatan: {row[1]}", color="#BDC3C7", size=11)
                                    ])
                                )
                            )
                    
                    if not ada_data:
                        pesan = "✅ Tidak ada truk yang Overtime." if sub == "overtime" else "✅ Area timbang kosong."
                        ACTIVE_UI["list_antrean"].controls.append(ft.Row([ft.Text(pesan, color="#2ECC71", italic=True)], alignment="center"))
                else:
                    ACTIVE_UI["list_antrean"].controls.append(ft.Row([ft.Text("✅ Area timbang kosong.", color="#2ECC71", italic=True)], alignment="center"))
            else:
                ACTIVE_UI["list_antrean"].controls.append(ft.Container(bgcolor="#311313", border_radius=8, padding=15, margin=10, content=ft.Row([ft.Text("⚠️", size=24), ft.Column([ft.Text("Disconnect dari Server", color="#E74C3C", size=14, weight="bold"), ft.Text("Periksa IP di Pengaturan.", color="#BDC3C7", size=11)])], spacing=15)))

        # --- UPDATE CHAT ---
        if halaman_aktif == "chat" and "list_chat" in ACTIVE_UI:
            ACTIVE_UI["list_chat"].controls.clear()
            if GLOBAL_DATA["db_status"] == "Konek DB":
                if GLOBAL_DATA["chat_history"]:
                    for r in reversed(GLOBAL_DATA["chat_history"]): # <== TAMBAHKAN reversed()
                        is_me = "Executive" in str(r[1]) 
                        bg_chat = "#27AE60" if is_me else "#2C3E50"
                        align = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START
                        
                        ACTIVE_UI["list_chat"].controls.append(
                            ft.Row([
                                ft.Container(bgcolor=bg_chat, padding=10, border_radius=10, width=250,
                                    content=ft.Column([
                                        ft.Text(f"{r[1]} - {r[0]}", color="#BDC3C7", size=9, weight="bold"),
                                        ft.Text(str(r[2]), color="white", size=12)
                                    ], spacing=2)
                                )
                            ], alignment=align)
                        )
                else:
                    ACTIVE_UI["list_chat"].controls.append(ft.Row([ft.Text("Belum ada riwayat pesan.", color="gray", italic=True)], alignment="center"))
            else:
                ACTIVE_UI["list_chat"].controls.append(ft.Row([ft.Text("⚠️ Database Disconnect", color="#E74C3C", italic=True)], alignment="center"))

        # --- UPDATE PENGATURAN ---
        if halaman_aktif == "pengaturan" and sub_halaman_aktif == "server" and "btn_koneksi" in ACTIVE_UI:
            if GLOBAL_DATA["db_status"] == "Konek DB":
                ACTIVE_UI["btn_koneksi"].content.controls[0].value = "🔌 Putuskan Koneksi"
                ACTIVE_UI["btn_koneksi"].bgcolor = "#C0392B"
            else:
                ACTIVE_UI["btn_koneksi"].content.controls[0].value = "💾 Simpan & Hubungkan"
                ACTIVE_UI["btn_koneksi"].bgcolor = "#27AE60"

        try: page.update()
        except: pass

    # ==========================================
    # MESIN SINKRONISASI DATABASE (Satu Pintu Aman)
    # ==========================================
    def tarik_data_database():
        with DB_LOCK:
            # =======================================================
            # REVISI: GEMBOK MASTER ANTI-NYAMBUNG OTOMATIS
            # =======================================================
            if GLOBAL_DATA["db_status"] == "Diputus":
                return
            # =======================================================
            
            cf_url = db_config.get("cf_url", "").strip()
            host = db_config.get("host", "").strip()
            port = int(db_config.get("port", 3306)) if str(db_config.get("port", "")).isdigit() else 3306
            user = db_config.get("user", "").strip()
            pwd = db_config.get("password", "")

            # ----------------------------------------------------
            # CABANG 1: JALUR ONLINE (API CLOUDFLARE)
            # ----------------------------------------------------
            if cf_url != "":
                try:
                    # Mengirimkan parameter filter ke server Ubuntu
                    payload = {
                        "tgl_awal": GLOBAL_DATA["tgl_awal"],
                        "tgl_akhir": GLOBAL_DATA["tgl_akhir"],
                        "filter_cari": GLOBAL_DATA["filter_cari"]
                    }
                    
                    # Memanggil API dengan batas waktu 5 detik
                    url_target = cf_url.rstrip("/") + "/api/get_data"
                    respon = requests.post(url_target, json=payload, timeout=5)
                    data_api = respon.json()

                    # Memperbarui GLOBAL_DATA dari respons API
                    GLOBAL_DATA["kas_masuk"] = data_api.get("kas_masuk", 0)
                    GLOBAL_DATA["kas_keluar"] = data_api.get("kas_keluar", 0)
                    GLOBAL_DATA["sisa_saldo"] = data_api.get("sisa_saldo", 0)
                    GLOBAL_DATA["bahan_baku"] = data_api.get("bahan_baku", {})
                    GLOBAL_DATA["produksi"] = data_api.get("produksi", {})
                    GLOBAL_DATA["top_5"] = data_api.get("top_5", [])
                    GLOBAL_DATA["tren_7_hari"] = data_api.get("tren_7_hari", []) # <== TAMBAHKAN INI
                    GLOBAL_DATA["trx_live"] = data_api.get("trx_live", [])
                    GLOBAL_DATA["trx_dibayar"] = data_api.get("trx_dibayar", [])
                    GLOBAL_DATA["trx_beli"] = data_api.get("trx_beli", [])
                    GLOBAL_DATA["trx_kirim"] = data_api.get("trx_kirim", [])
                    GLOBAL_DATA["mst_suplier"] = data_api.get("mst_suplier", [])
                    GLOBAL_DATA["mst_customer"] = data_api.get("mst_customer", [])
                    GLOBAL_DATA["mst_harga"] = data_api.get("mst_harga", [])
                    GLOBAL_DATA["list_komoditas"] = data_api.get("list_komoditas", [])
                    GLOBAL_DATA["antrean"] = data_api.get("antrean", [])
                    GLOBAL_DATA["chat_history"] = data_api.get("chat_history", [])

                    GLOBAL_DATA["db_status"] = "Konek DB"
                    GLOBAL_DATA["db_color"] = "#2ECC71"
                    return # Berhenti di sini, tidak lanjut ke mode lokal
                
                except Exception as e:
                    GLOBAL_DATA["db_status"] = "Disconnect"
                    GLOBAL_DATA["db_color"] = "#E74C3C"
                    return # Gagal konek API, proses dihentikan

            # ----------------------------------------------------
            # CABANG 2: JALUR LOKAL (MySQL MENTAH)
            # ----------------------------------------------------
            if not host or GLOBAL_DATA["db_status"] == "Diputus":
                GLOBAL_DATA["db_status"] = "Disconnect"
                GLOBAL_DATA["db_color"] = "#E74C3C"
                return
            
            if not HAS_MYSQL:
                GLOBAL_DATA["db_status"] = "Modul Error"
                GLOBAL_DATA["db_color"] = "#E74C3C"
                return

            try:
                conn = mysql.connector.connect(host=host, port=port, user=user, password=pwd, database="db_timbangan", connect_timeout=3)
                cursor = conn.cursor()

                # =======================================================
                # REVISI: FILTER BULAN INI AGAR RESET SETIAP AWAL BULAN
                # =======================================================
                bln_ini = datetime.now().strftime("%Y-%m")
                
                # --- 1. SALDO AKTUAL (SEMUA WAKTU / TIDAK DIRESET) ---
                cursor.execute("SELECT SUM(nominal) FROM buku_kas WHERE jenis='Pemasukan'")
                masuk_all = float(cursor.fetchone()[0] or 0)
                
                cursor.execute("SELECT SUM(nominal) FROM buku_kas WHERE jenis='Pengeluaran'")
                keluar_all_ops = float(cursor.fetchone()[0] or 0)
                
                cursor.execute("SELECT SUM(total_harga) FROM transaksi WHERE mode='Pembelian' AND status_bayar='Lunas'")
                keluar_all_tbs = float(cursor.fetchone()[0] or 0)
                
                GLOBAL_DATA["sisa_saldo"] = masuk_all - (keluar_all_ops + keluar_all_tbs)

                # --- 2. KAS MASUK & KELUAR (HANYA BULAN INI) ---
                cursor.execute("SELECT SUM(nominal) FROM buku_kas WHERE jenis='Pemasukan' AND LEFT(tanggal, 7)=%s", (bln_ini,))
                GLOBAL_DATA["kas_masuk"] = float(cursor.fetchone()[0] or 0)
                
                cursor.execute("SELECT SUM(nominal) FROM buku_kas WHERE jenis='Pengeluaran' AND LEFT(tanggal, 7)=%s", (bln_ini,))
                keluar_ops_bln = float(cursor.fetchone()[0] or 0)
                
                cursor.execute("SELECT SUM(total_harga) FROM transaksi WHERE mode='Pembelian' AND status_bayar='Lunas' AND LEFT(tanggal, 7)=%s", (bln_ini,))
                keluar_tbs_bln = float(cursor.fetchone()[0] or 0)
                
                GLOBAL_DATA["kas_keluar"] = keluar_ops_bln + keluar_tbs_bln

                # --- 3. TONASE & TOP 5 (HANYA BULAN INI) ---
                cursor.execute("SELECT nama, kategori FROM master_komoditas WHERE status='Aktif'")
                master_komoditas = cursor.fetchall()
                list_kat_masuk = [r[0] for r in master_komoditas if "Masuk" in str(r[1])]
                list_kat_keluar = [r[0] for r in master_komoditas if "Keluar" in str(r[1])]
                # SUNTIKAN: Simpan daftar nama ke memori global
                GLOBAL_DATA["list_komoditas"] = [r[0] for r in master_komoditas]

                cursor.execute("SELECT jenis_barang, SUM(total_netto) FROM transaksi WHERE LEFT(tanggal, 7)=%s GROUP BY jenis_barang", (bln_ini,))
                agregat_tonase = dict(cursor.fetchall())
                GLOBAL_DATA["bahan_baku"] = {k: float(agregat_tonase.get(k, 0)) for k in list_kat_masuk}
                GLOBAL_DATA["produksi"] = {k: float(agregat_tonase.get(k, 0)) for k in list_kat_keluar}

                cursor.execute("SELECT no_do, SUM(total_netto) as tot FROM transaksi WHERE mode='Pembelian' AND LEFT(tanggal, 7)=%s GROUP BY no_do ORDER BY tot DESC LIMIT 5", (bln_ini,))
                GLOBAL_DATA["top_5"] = cursor.fetchall()
                # =======================================================

                # --- TAMBAHAN SQL TREN 7 HARI (LOKAL) ---
                cursor.execute("""
                    SELECT 
                        DATE_FORMAT(tanggal, '%m-%d') as tgl,
                        SUM(CASE WHEN mode='Pembelian' THEN total_netto ELSE 0 END) as masuk,
                        SUM(CASE WHEN mode='Pengiriman' THEN total_netto ELSE 0 END) as keluar
                    FROM transaksi 
                    WHERE tanggal >= CURDATE() - INTERVAL 6 DAY
                    GROUP BY DATE_FORMAT(tanggal, '%m-%d')
                    ORDER BY tgl ASC
                """)
                GLOBAL_DATA["tren_7_hari"] = cursor.fetchall()

                # =======================================================
                # SINKRONISASI DATA PENCARIAN & FILTER REGULER
                # =======================================================
                t_awal = GLOBAL_DATA["tgl_awal"]
                t_akhir = GLOBAL_DATA["tgl_akhir"]
                kunci = f"%{GLOBAL_DATA['filter_cari']}%"

                cursor.execute("SELECT no_transaksi, no_polisi, total_netto, status_bayar, IFNULL(nama_supir, '-'), IFNULL(no_do, '-') FROM transaksi WHERE DATE(tanggal) = CURDATE() AND (IFNULL(no_do, '') LIKE %s OR IFNULL(no_polisi, '') LIKE %s) ORDER BY jam_keluar DESC LIMIT 50", (kunci, kunci))
                GLOBAL_DATA["trx_live"] = cursor.fetchall()
                
                cursor.execute("SELECT no_invoice, nama_supplier, total_netto, total_uang, tanggal FROM tabel_invoice WHERE SUBSTRING(tanggal, 1, 10) BETWEEN %s AND %s AND IFNULL(nama_supplier, '') LIKE %s ORDER BY tanggal DESC LIMIT 100", (t_awal, t_akhir, kunci))
                GLOBAL_DATA["trx_dibayar"] = cursor.fetchall()
                
                cursor.execute("SELECT no_transaksi, no_polisi, IFNULL(nama_supir, '-'), total_netto, IFNULL(no_do, '-') FROM transaksi WHERE mode='Pembelian' AND SUBSTRING(tanggal, 1, 10) BETWEEN %s AND %s AND (IFNULL(no_do, '') LIKE %s OR IFNULL(no_polisi, '') LIKE %s) ORDER BY jam_keluar DESC LIMIT 100", (t_awal, t_akhir, kunci, kunci))
                GLOBAL_DATA["trx_beli"] = cursor.fetchall()
                
                cursor.execute("SELECT no_transaksi, no_polisi, IFNULL(nama_supir, '-'), total_netto, IFNULL(no_do, '-') FROM transaksi WHERE mode='Pengiriman' AND SUBSTRING(tanggal, 1, 10) BETWEEN %s AND %s AND (IFNULL(no_do, '') LIKE %s OR IFNULL(no_polisi, '') LIKE %s) ORDER BY jam_keluar DESC LIMIT 100", (t_awal, t_akhir, kunci, kunci))
                GLOBAL_DATA["trx_kirim"] = cursor.fetchall()

                cursor.execute("SELECT kode, nama, tipe, kontak, status FROM master_supplier WHERE status='Aktif' AND tipe IN ('Umum', 'Petani Mandiri', 'Pengepul / RAM', 'Koperasi / Plasma') AND nama != 'Pelanggan Umum' LIMIT 100")
                GLOBAL_DATA["mst_suplier"] = cursor.fetchall()
                
                cursor.execute("SELECT kode, nama, tipe, kontak, status FROM master_supplier WHERE status='Aktif' AND (tipe='Pabrik Pembeli PKS' OR nama='Pelanggan Umum') LIMIT 100")
                GLOBAL_DATA["mst_customer"] = cursor.fetchall()
                
                # =======================================================
                # PERBAIKAN: FORMAT 7 KOLOM HARGA AGAR POP-UP INSTAN
                # =======================================================
                cursor.execute("SELECT kode, tanggal, komoditas, tipe_supplier, IFNULL(nama_supplier, '- Berlaku Semua -'), nominal, status FROM master_harga WHERE status='Aktif' ORDER BY tanggal DESC LIMIT 50")
                GLOBAL_DATA["mst_harga"] = cursor.fetchall()

                cursor.execute("SELECT no_polisi, jenis_barang, jam_masuk FROM antrian ORDER BY jam_masuk DESC")
                GLOBAL_DATA["antrean"] = cursor.fetchall()

                cursor.execute("SELECT waktu, pengirim, pesan FROM tabel_chat ORDER BY id DESC LIMIT 50")
                GLOBAL_DATA["chat_history"] = cursor.fetchall()

                conn.close()
                GLOBAL_DATA["db_status"] = "Konek DB"
                GLOBAL_DATA["db_color"] = "#2ECC71"

            except Exception as e:
                GLOBAL_DATA["db_status"] = "Disconnect"
                GLOBAL_DATA["db_color"] = "#E74C3C"

    def robot_penyedot_otomatis():
        while True:
            # Pengecekan HAS_MYSQL dipindahkan ke dalam agar skrip tetap 
            # bisa menarik data API dari HP meskipun modul lokal error.
            tarik_data_database()
            update_live_ui()
            jeda = int(db_config.get("refresh_interval", 3))
            time.sleep(jeda)

    # Robot sengaja dimatikan saat awal agar tidak membebani layar Welcome.
    # threading.Thread(target=robot_penyedot_otomatis, daemon=True).start()

    # ==========================================
    # SISTEM NAVIGASI & RENDER HALAMAN
    # ==========================================
    def pindah_menu(nama, sub=""):
        nonlocal halaman_aktif, sub_halaman_aktif
        
        if nama != halaman_aktif:
            GLOBAL_DATA["tgl_awal"] = tgl_hari_ini
            GLOBAL_DATA["tgl_akhir"] = tgl_hari_ini
            GLOBAL_DATA["filter_cari"] = ""
            
        halaman_aktif = nama
        sub_halaman_aktif = sub
        
        page.controls.clear()
        ACTIVE_UI.clear() 

        # ----------------------------------------------------
        # MENU BAWAH SLIM MODE EKSTREM (SANGAT RAMPING)
        # ----------------------------------------------------
        def tombol_menu(ikon, teks, target):
            warna = "#3498DB" if halaman_aktif == target else "#BDC3C7"
            tebal = "bold" if halaman_aktif == target else "normal"
            
            # PENTING: Penggunaan padding wajib menggunakan integer mutlak (bukan padding.only)
            # agar aman 100% saat dikompilasi ke APK Android[cite: 2].
            if target == "chat":
                return ft.Container(
                    content=ft.Column([ft.Text(ikon, size=16), ft.Text(teks, size=8, color="white", weight=tebal)], horizontal_alignment="center", spacing=0),
                    bgcolor="#E67E22" if halaman_aktif != "chat" else "#D35400",
                    on_click=lambda e: pindah_menu(target), ink=True, padding=5, border_radius=15, height=45
                )

            return ft.Container(
                content=ft.Column([ft.Text(ikon, size=16), ft.Text(teks, size=8, color=warna, weight=tebal)], horizontal_alignment="center", spacing=0),
                on_click=lambda e: pindah_menu(target), ink=True, padding=2, height=45
            )

        menu_bawah = ft.Container(
            bgcolor="#141a29", padding=2, height=55, 
            content=ft.Row([
                tombol_menu("📊", "Dashboard", "dashboard"), 
                tombol_menu("🧾", "Transaksi", "transaksi"), 
                tombol_menu("💬", "Chat", "chat"),
                tombol_menu("🚚", "Antrean", "antrean"), 
                tombol_menu("⚙️", "Pengaturan", "pengaturan")
            ], alignment="spaceAround")
        )

        # ==========================================
        # KONTEN HALAMAN: DASHBOARD 
        # ==========================================
        if halaman_aktif == "dashboard":
            ind_warna = ft.Container(width=12, height=12, border_radius=6, bgcolor=GLOBAL_DATA["db_color"])
            ACTIVE_UI["ind_warna"] = ind_warna

            # 1. HEADER (Kini terpisah agar tidak ikut tergulung)
            header = ft.Container(bgcolor="#141a29", padding=20, content=ft.Row([ft.Row([ft.Image(src="logo.png", width=30, height=30, fit="contain"), ft.Text("NMC", weight="bold", size=20, color="#3498DB"), ft.Text("Executive", size=20, color="white")], alignment="start", spacing=8), ind_warna], alignment="spaceBetween"))

            txt_kas_masuk = ft.Text("Rp 0", color="#2ECC71", weight="bold")
            txt_kas_keluar = ft.Text("Rp 0", color="#E74C3C", weight="bold")
            txt_sisa_saldo = ft.Text("Rp 0", weight="bold", color="#3498DB", size=18)
            
            ACTIVE_UI["txt_kas_masuk"] = txt_kas_masuk
            ACTIVE_UI["txt_kas_keluar"] = txt_kas_keluar
            ACTIVE_UI["txt_sisa_saldo"] = txt_sisa_saldo

            # --- KARTU BARU: TREN 7 HARI ---
            list_tren = ft.Column([ft.Row([ft.Text("Menunggu Sinkronisasi...", color="gray")], alignment="center")])
            ACTIVE_UI["list_tren"] = list_tren
            card_tren = ft.Container(bgcolor="#141A29", padding=20, border_radius=12, margin=15, content=ft.Column([ft.Text("📈 TREN TONASE (7 HARI TERAKHIR)", weight="bold", color="#2ECC71"), ft.Divider(color="#2C3E50"), list_tren]))

            # --- KARTU LAMA: INFORMASI KAS ---
            card_kasir = ft.Container(bgcolor="#141A29", padding=20, border_radius=12, margin=15, content=ft.Column([ft.Text("💰 INFORMASI KAS (LIVE)", weight="bold", color="#F1C40F"), ft.Divider(color="#2C3E50"), ft.Row([ft.Text("Kas Masuk", color="#BDC3C7"), txt_kas_masuk], alignment="spaceBetween"), ft.Row([ft.Text("Kas Keluar", color="#BDC3C7"), txt_kas_keluar], alignment="spaceBetween"), ft.Divider(color="#2C3E50"), ft.Row([ft.Text("SISA SALDO", color="white", weight="bold", size=14), txt_sisa_saldo], alignment="spaceBetween")]))

            # --- KARTU LAMA: BAHAN BAKU ---
            list_bahan_baku = ft.Column([ft.Row([ft.Text("Menunggu Sinkronisasi...", color="gray")], alignment="center")])
            ACTIVE_UI["list_bahan_baku"] = list_bahan_baku
            card_bahan_baku = ft.Container(bgcolor="#141A29", padding=20, border_radius=12, margin=15, content=ft.Column([ft.Text("📥 BAHAN BAKU (MASUK)", weight="bold", color="#2ECC71"), ft.Divider(color="#2C3E50"), list_bahan_baku]))

            # --- KARTU LAMA: PROPORSI PRODUKSI ---
            list_produksi = ft.Column([ft.Row([ft.Text("Menunggu Sinkronisasi...", color="gray")], alignment="center")])
            ACTIVE_UI["list_produksi"] = list_produksi
            card_produksi = ft.Container(bgcolor="#141A29", padding=20, border_radius=12, margin=15, content=ft.Column([ft.Text("📤 PROPORSI PRODUKSI (KELUAR)", weight="bold", color="#9B59B6"), ft.Divider(color="#2C3E50"), list_produksi]))

            # --- KARTU LAMA: TOP 5 ---
            list_top5 = ft.Column([ft.Row([ft.Text("Menunggu Sinkronisasi...", color="gray")], alignment="center")])
            ACTIVE_UI["list_top5"] = list_top5
            card_top_5 = ft.Container(bgcolor="#141A29", padding=20, border_radius=12, margin=15, content=ft.Column([ft.Text("🏆 TOP 5 SUPPLIER", weight="bold", color="#E67E22"), ft.Divider(color="#2C3E50"), list_top5]))

            # 2. KONTEN DATA (Menambahkan card_tren tepat sebelum card_kasir di urutan layarnya)
            konten_scroll = ft.Column([card_tren, card_kasir, card_bahan_baku, card_produksi, card_top_5, ft.Container(height=10)], scroll="auto", expand=True)

            # 3. PENGGABUNGAN (Header tetap di atas, Konten bisa digulung di bawahnya)
            area_tengah = ft.Column([header, konten_scroll], expand=True, spacing=0)

        # ==========================================
        # KONTEN HALAMAN: TRANSAKSI 
        # ==========================================
        elif halaman_aktif == "transaksi":
            sub = sub_halaman_aktif if sub_halaman_aktif else "tiket" 
            
            ind_warna = ft.Container(width=12, height=12, border_radius=6, bgcolor=GLOBAL_DATA["db_color"])
            ACTIVE_UI["ind_warna"] = ind_warna

            header_transaksi = ft.Container(bgcolor="#141A29", padding=20, content=ft.Column([ft.Row([ft.Row([ft.Image(src="logo.png", width=25, height=25, fit="contain"), ft.Text("Pusat Data", weight="bold", size=18, color="white")], spacing=10), ind_warna], alignment="spaceBetween")]))

            def buat_tab(ikon, teks, target_sub):
                bg_warna = "#3498DB" if sub == target_sub else "#2C3E50"
                return ft.Container(content=ft.Row([ft.Text(ikon, size=14), ft.Text(teks, color="white", weight="bold", size=12)], alignment="center"), bgcolor=bg_warna, padding=10, border_radius=8, ink=True, on_click=lambda e: pindah_menu("transaksi", target_sub), expand=True)

            menu_tab = ft.Container(padding=15, content=ft.Column([
                ft.Row([buat_tab("🎫", "Tiket Live", "tiket"), buat_tab("💸", "Dibayar", "pembayaran")], spacing=10),
                ft.Row([buat_tab("📥", "Lap. Beli", "lap_beli"), buat_tab("📤", "Lap. Kirim", "lap_kirim")], spacing=10),
                ft.Row([buat_tab("🤝", "Cust & Supl", "suplier"), buat_tab("🏷️", "Harga", "harga")], spacing=10), 
            ], spacing=10))

            inp_tgl_awal = ft.TextField(value=GLOBAL_DATA["tgl_awal"], hint_text="YYYY-MM-DD", width=110, height=35, text_size=11, content_padding=8, bgcolor="#0A1128", border_color="#3498DB", color="white")
            inp_tgl_akhir = ft.TextField(value=GLOBAL_DATA["tgl_akhir"], hint_text="YYYY-MM-DD", width=110, height=35, text_size=11, content_padding=8, bgcolor="#0A1128", border_color="#3498DB", color="white")
            inp_cari_nama = ft.TextField(value=GLOBAL_DATA["filter_cari"], hint_text="Cari Nama/Nopol...", expand=True, height=35, text_size=11, content_padding=8, bgcolor="#0A1128", border_color="#3498DB", color="white")

            def eksekusi_filter_kilat(e):
                GLOBAL_DATA["tgl_awal"] = inp_tgl_awal.value
                GLOBAL_DATA["tgl_akhir"] = inp_tgl_akhir.value
                GLOBAL_DATA["filter_cari"] = inp_cari_nama.value
                
                ACTIVE_UI["list_transaksi"].controls.clear()
                ACTIVE_UI["list_transaksi"].controls.append(ft.Row([ft.Text("⏳ Menyedot Data...", color="#F1C40F", italic=True)], alignment="center"))
                try: page.update()
                except: pass

                if HAS_MYSQL: tarik_data_database()
                update_live_ui() 

            btn_terapkan = ft.Container(content=ft.Text("Terapkan", color="white", weight="bold", size=11), bgcolor="#27AE60", padding=8, border_radius=5, ink=True, on_click=eksekusi_filter_kilat)

            row_tanggal = ft.Row([ft.Text("Dari:", color="#BDC3C7", size=11), inp_tgl_awal, ft.Text(" S/d:", color="#BDC3C7", size=11), inp_tgl_akhir], alignment="center", visible=(sub != "tiket"))

            # --- SUNTIKAN TOMBOL + TAMBAH ---
            btn_tambah = ft.Container(content=ft.Text("+ Tambah", color="white", weight="bold", size=11), bgcolor="#8E44AD", padding=8, border_radius=5, ink=True, on_click=lambda e: buka_form_master("supplier" if sub == "suplier" else "harga", "tambah"), visible=(sub in ["suplier", "harga"]))

            filter_area = ft.Container(
                padding=15,
                content=ft.Column([
                    row_tanggal,
                    # Tampilkan tombol tambah di baris pencarian
                    ft.Row([inp_cari_nama, btn_terapkan, btn_tambah], spacing=10) 
                ], spacing=10),
                # Buka Filter untuk Suplier & Harga
                visible=(sub in ["tiket", "pembayaran", "lap_beli", "lap_kirim", "suplier", "harga"]) 
            )

            list_transaksi = ft.Column([ft.Row([ft.Text("⏳ Menyinkronkan...", color="gray", italic=True)], alignment="center")], spacing=10)
            ACTIVE_UI["list_transaksi"] = list_transaksi
            
            area_tengah = ft.Column([header_transaksi, menu_tab, filter_area, ft.Container(padding=15, content=list_transaksi)], scroll="auto", expand=True)

        # ==========================================
        # KONTEN HALAMAN: ANTREAN 
        # ==========================================
        elif halaman_aktif == "antrean":
            sub = sub_halaman_aktif if sub_halaman_aktif else "dalam_area"

            ind_warna = ft.Container(width=12, height=12, border_radius=6, bgcolor=GLOBAL_DATA["db_color"])
            ACTIVE_UI["ind_warna"] = ind_warna

            header_antrean = ft.Container(bgcolor="#141A29", padding=20, content=ft.Column([ft.Row([ft.Row([ft.Image(src="logo.png", width=25, height=25, fit="contain"), ft.Text("Live Yard", weight="bold", size=18, color="white")], spacing=10), ind_warna], alignment="spaceBetween"), ft.Text("Pantau arus kendaraan di dalam pabrik.", color="#BDC3C7", size=12)]))

            def buat_tab_antrean(ikon, teks, target_sub):
                bg_warna = "#9B59B6" if sub == target_sub else "#2C3E50" 
                return ft.Container(content=ft.Row([ft.Text(ikon, size=14), ft.Text(teks, color="white", weight="bold", size=14)], alignment="center"), bgcolor=bg_warna, padding=15, border_radius=8, ink=True, on_click=lambda e: pindah_menu("antrean", target_sub), expand=True)

            menu_tab_antrean = ft.Container(padding=15, content=ft.Row([buat_tab_antrean("🏭", "Dalam Area", "dalam_area"), buat_tab_antrean("🚨", "Overtime", "overtime")], spacing=10))

            list_antrean = ft.Column([ft.Row([ft.Text("⏳ Menyinkronkan...", color="gray", italic=True)], alignment="center")], spacing=10)
            ACTIVE_UI["list_antrean"] = list_antrean

            area_tengah = ft.Column([header_antrean, menu_tab_antrean, ft.Container(padding=15, content=list_antrean)], scroll="auto", expand=True)

        # ==========================================
        # KONTEN HALAMAN: CHAT INTERNAL
        # ==========================================
        elif halaman_aktif == "chat":
            ind_warna = ft.Container(width=12, height=12, border_radius=6, bgcolor=GLOBAL_DATA["db_color"])
            ACTIVE_UI["ind_warna"] = ind_warna
            
            header_chat = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([ft.Text("💬 Chat Internal Pabrik", weight="bold", size=16, color="white"), ind_warna], alignment="spaceBetween"))
            
            list_chat = ft.Column([], scroll="auto", auto_scroll=True, expand=True, spacing=10)
            ACTIVE_UI["list_chat"] = list_chat
            
            inp_pesan = ft.TextField(hint_text="Ketik pesan...", expand=True, bgcolor="#0A1128", border_color="#3498DB", color="white", height=40, content_padding=10)
            
            def kirim_pesan(e):
                pesan = inp_pesan.value.strip()
                if not pesan: return
                inp_pesan.value = ""
                try: page.update()
                except: pass
                
                def eksekusi_kirim():
                    cf_url = db_config.get("cf_url", "").strip()
                    waktu_skrg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # REVISI: Mengambil nama dari pengaturan dan menggabungkannya
                    nama_tambahan = db_config.get("nama_user", "").strip()
                    nama_pengirim = f"NMC Executive : {nama_tambahan}" if nama_tambahan else "NMC Executive"

                    # ----------------------------------------------------
                    # CABANG 1: JALUR ONLINE (API CLOUDFLARE)
                    # ----------------------------------------------------
                    if cf_url != "":
                        try:
                            payload_chat = {
                                "pengirim": nama_pengirim, # <== MENGGUNAKAN NAMA DINAMIS
                                "pesan": pesan,
                                "waktu": waktu_skrg
                            }
                            url_target = cf_url.rstrip("/") + "/api/kirim_chat"
                            requests.post(url_target, json=payload_chat, timeout=5)
                        except: pass
                        
                    # ----------------------------------------------------
                    # CABANG 2: JALUR LOKAL (MySQL MENTAH)
                    # ----------------------------------------------------
                    else:
                        if not HAS_MYSQL: return
                        try:
                            conn = mysql.connector.connect(host=db_config["host"], port=int(db_config["port"]), user=db_config["user"], password=db_config["password"], database="db_timbangan", connect_timeout=3)
                            cursor = conn.cursor()
                            
                            # REVISI: Mengganti 'NMC Executive' statis dengan variabel nama_pengirim
                            cursor.execute("INSERT INTO tabel_chat (waktu, pengirim, pesan) VALUES (%s, %s, %s)", (waktu_skrg, nama_pengirim, pesan))
                            
                            conn.commit()
                            conn.close()
                        except: pass
                    
                    tarik_data_database()
                    update_live_ui()
                
                threading.Thread(target=eksekusi_kirim, daemon=True).start()

            btn_kirim = ft.Container(content=ft.Text("Kirim", color="white", weight="bold"), bgcolor="#3498DB", padding=10, border_radius=8, ink=True, on_click=kirim_pesan)
            area_bawah = ft.Container(bgcolor="#141a29", padding=15, content=ft.Row([inp_pesan, btn_kirim], spacing=10))

            area_tengah = ft.Column([header_chat, ft.Container(padding=15, content=list_chat, expand=True), area_bawah], expand=True)

        # ==========================================
        # KONTEN HALAMAN: PENGATURAN 
        # ==========================================
        elif halaman_aktif == "pengaturan":
            if sub_halaman_aktif == "":
                header_setting = ft.Container(
                    padding=20, 
                    content=ft.Column([
                        ft.Row([
                            ft.Image(src="logo.png", width=35, height=35, fit="contain"), 
                            ft.Text("Pusat Kendali", weight="bold", size=22, color="white")
                        ], spacing=15), 
                        ft.Container(height=5), 
                        ft.Text("Atur parameter integrasi Cloudflare.", color="#BDC3C7", size=13)
                    ])
                )

                def buat_list_setting(ikon, judul, deskripsi, target_sub):
                    return ft.Container(
                        bgcolor="#141a29", padding=20, border_radius=12, margin=10, ink=True, 
                        on_click=lambda e: pindah_menu("pengaturan", target_sub), 
                        content=ft.Row([
                            ft.Text(ikon, size=24), ft.Container(width=10), 
                            ft.Column([
                                ft.Text(judul, weight="bold", color="white", size=16), 
                                ft.Text(deskripsi, color="#BDC3C7", size=11)
                            ], spacing=2, expand=True), 
                            ft.Text("➔", color="#3498DB", size=18, weight="bold")
                        ])
                    )


                def aksi_keluar_aplikasi(e):
                    import os
                    os._exit(0) # Perintah mutlak untuk membunuh proses aplikasi dan robot seketika
                    
                list_menu_pengaturan = ft.Column([
                    buat_list_setting("👤", "Profil Pengguna", "Atur identitas Anda di obrolan Chat", "profil"),
                    buat_list_setting("🌐", "Konfigurasi Server", "Atur IP Database, Port & Koneksi Cloudflare", "server"),
                    buat_list_setting("⏱️", "Sinkronisasi Data", "Atur interval refresh data otomatis", "sinkronisasi"),
                    buat_list_setting("⏳", "Batas Overtime", "Atur batas waktu tunggu kendaraan (Jam)", "overtime"),
                    buat_list_setting("ℹ️", "Tentang Aplikasi", "Versi perangkat lunak & Informasi Lisensi", "about"),
                    ft.Container(height=15),
                    ft.Container(
                        content=ft.Row([ft.Text("🚪 KELUAR APLIKASI", color="white", weight="bold", size=14)], alignment="center"), 
                        bgcolor="#C0392B", padding=15, border_radius=12, margin=15, ink=True, 
                        on_click=aksi_keluar_aplikasi
                    ),
                    ft.Container(height=20)
                ], spacing=0)

                area_tengah = ft.Column([header_setting, list_menu_pengaturan], scroll="auto", expand=True)

            elif sub_halaman_aktif == "server":
                inp_host = ft.TextField(label="Host / IP Server", value=db_config.get("host", ""), bgcolor="#141A29", border_color="#3498DB", color="white")
                inp_port = ft.TextField(label="Port MySQL", value=db_config.get("port", "3306"), bgcolor="#141A29", border_color="#3498DB", color="white")
                inp_user = ft.TextField(label="Username DB", value=db_config.get("user", "root"), bgcolor="#141A29", border_color="#3498DB", color="white")
                inp_pass = ft.TextField(label="Password DB", value=db_config.get("password", ""), password=True, can_reveal_password=True, bgcolor="#141A29", border_color="#3498DB", color="white")
                inp_cf = ft.TextField(label="URL Cloudflare", value=db_config.get("cf_url", ""), hint_text="Kosongkan jika di Jaringan Lokal", bgcolor="#141A29", border_color="#3498DB", color="white")
                
                lbl_status_simpan = ft.Text("", size=12, weight="bold")
                btn_koneksi = ft.Container(content=ft.Row([ft.Text("...", color="white", weight="bold")], alignment="center"), padding=15, border_radius=8, ink=True)
                ACTIVE_UI["btn_koneksi"] = btn_koneksi

                def aksi_tombol_koneksi(e):
                    if GLOBAL_DATA["db_status"] == "Konek DB":
                        GLOBAL_DATA["db_status"] = "Diputus"
                        GLOBAL_DATA["db_color"] = "#E74C3C"
                        
                        # LOGIKA YANG DIHAPUS:
                        # db_config["host"] = ""  <-- Ini biang keladi yang menghapus IP Bapak!
                        # simpan_pengaturan(db_config)
                        
                        lbl_status_simpan.value = "⚠️ Koneksi Diputus (Konfigurasi Tetap Tersimpan)."
                        lbl_status_simpan.color = "#E74C3C"
                        update_live_ui()
                    else:
                        db_config["host"] = inp_host.value.strip()
                        db_config["port"] = inp_port.value.strip()
                        db_config["user"] = inp_user.value.strip()
                        db_config["password"] = inp_pass.value
                        db_config["cf_url"] = inp_cf.value.strip()
                        simpan_pengaturan(db_config)
                        
                        lbl_status_simpan.value = "⏳ Menghubungkan ke Server..."
                        lbl_status_simpan.color = "#F1C40F"
                        
                        # =======================================================
                        # REVISI: BUKA KEMBALI GEMBOK AGAR BISA TERHUBUNG
                        # =======================================================
                        GLOBAL_DATA["db_status"] = "Menghubungkan..."
                        
                        try: page.update()
                        except: pass
                        
                        tarik_data_database()
                        
                        if GLOBAL_DATA["db_status"] == "Konek DB":
                            lbl_status_simpan.value = "✅ Tersimpan & Terhubung!"
                            lbl_status_simpan.color = "#2ECC71"
                        else:
                            lbl_status_simpan.value = "⚠️ Gagal Terhubung."
                            lbl_status_simpan.color = "#E74C3C"
                        update_live_ui()

                btn_koneksi.on_click = aksi_tombol_koneksi

                btn_kembali = ft.Container(content=ft.Row([ft.Text("⬅️ Kembali", color="#BDC3C7", weight="bold")]), padding=10, ink=True, on_click=lambda e: pindah_menu("pengaturan", ""))
                header_server = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([btn_kembali, ft.Text("Konfigurasi Server", weight="bold", size=16, color="white")]))

                form_server = ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Lokal/LAN: Gunakan IP Lokal & Port 3306. Cloudflare URL dikosongkan.", color="#BDC3C7", size=12),
                        ft.Container(height=15), inp_host, inp_port, inp_user, inp_pass, inp_cf, ft.Container(height=15),
                        btn_koneksi,
                        ft.Container(height=5), ft.Row([lbl_status_simpan], alignment="center")
                    ])
                )
                area_tengah = ft.Column([header_server, form_server], scroll="auto", expand=True)

            elif sub_halaman_aktif == "sinkronisasi":
                val_interval = str(db_config.get("refresh_interval", "3"))
                
                dd_interval = ft.Dropdown(
                    label="Interval Refresh Data",
                    value=val_interval,
                    options=[
                        ft.dropdown.Option("1", "1 Detik (Sangat Cepat)"),
                        ft.dropdown.Option("3", "3 Detik (Normal)"),
                        ft.dropdown.Option("5", "5 Detik (Sedang)"),
                        ft.dropdown.Option("10", "10 Detik (Santai)"),
                    ],
                    bgcolor="#141A29", border_color="#3498DB", color="white"
                )
                
                lbl_status_sync = ft.Text("", size=12, weight="bold")
                
                def simpan_interval(e):
                    db_config["refresh_interval"] = dd_interval.value
                    simpan_pengaturan(db_config)
                    lbl_status_sync.value = f"✅ Robot akan me-refresh layar tiap {dd_interval.value} detik."
                    lbl_status_sync.color = "#2ECC71"
                    try: page.update()
                    except: pass
                    
                btn_simpan_sync = ft.Container(
                    content=ft.Row([ft.Text("💾 Simpan Setelan", color="white", weight="bold")], alignment="center"), 
                    bgcolor="#27AE60", padding=15, border_radius=8, ink=True, on_click=simpan_interval
                )
                
                btn_kembali = ft.Container(content=ft.Row([ft.Text("⬅️ Kembali", color="#BDC3C7", weight="bold")]), padding=10, ink=True, on_click=lambda e: pindah_menu("pengaturan", ""))
                header_sync = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([btn_kembali, ft.Text("Sinkronisasi Data", weight="bold", size=16, color="white")]))

                form_sync = ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Atur seberapa sering robot menyedot data dari Database Server.", color="#BDC3C7", size=12),
                        ft.Container(height=15), dd_interval, ft.Container(height=15),
                        btn_simpan_sync,
                        ft.Container(height=5), ft.Row([lbl_status_sync], alignment="center")
                    ])
                )
                area_tengah = ft.Column([header_sync, form_sync], scroll="auto", expand=True)

            elif sub_halaman_aktif == "overtime":
                val_ot = str(db_config.get("overtime_limit", "2.0"))
                
                dd_overtime = ft.Dropdown(
                    label="Batas Waktu Overtime (Jam)",
                    value=val_ot,
                    options=[
                        ft.dropdown.Option("1.0", "1 Jam (Ketat)"),
                        ft.dropdown.Option("1.5", "1.5 Jam"),
                        ft.dropdown.Option("2.0", "2 Jam (Standar)"),
                        ft.dropdown.Option("3.0", "3 Jam"),
                        ft.dropdown.Option("4.0", "4 Jam"),
                        ft.dropdown.Option("5.0", "5 Jam (Sangat Longgar)"),
                    ],
                    bgcolor="#141A29", border_color="#3498DB", color="white"
                )
                
                lbl_status_ot = ft.Text("", size=12, weight="bold")
                
                def simpan_ot(e):
                    db_config["overtime_limit"] = dd_overtime.value
                    simpan_pengaturan(db_config)
                    lbl_status_ot.value = f"✅ Batas Overtime disetel ke {dd_overtime.value} Jam."
                    lbl_status_ot.color = "#2ECC71"
                    try: page.update()
                    except: pass
                    
                btn_simpan_ot = ft.Container(
                    content=ft.Row([ft.Text("💾 Simpan Setelan", color="white", weight="bold")], alignment="center"), 
                    bgcolor="#27AE60", padding=15, border_radius=8, ink=True, on_click=simpan_ot
                )
                
                btn_kembali = ft.Container(content=ft.Row([ft.Text("⬅️ Kembali", color="#BDC3C7", weight="bold")]), padding=10, ink=True, on_click=lambda e: pindah_menu("pengaturan", ""))
                header_ot = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([btn_kembali, ft.Text("Batas Overtime", weight="bold", size=16, color="white")]))

                form_ot = ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Truk yang menunggu di dalam area pabrik melebihi batas waktu ini akan ditandai merah dan masuk ke tab Overtime.", color="#BDC3C7", size=12),
                        ft.Container(height=15), dd_overtime, ft.Container(height=15),
                        btn_simpan_ot,
                        ft.Container(height=5), ft.Row([lbl_status_ot], alignment="center")
                    ])
                )
                area_tengah = ft.Column([header_ot, form_ot], scroll="auto", expand=True)

            elif sub_halaman_aktif == "profil":
                val_nama = db_config.get("nama_user", "")
                
                inp_nama = ft.TextField(
                    label="Nama Anda (Kosongkan jika ingin default)",
                    value=val_nama,
                    hint_text="Contoh: Bos Dzamrud",
                    bgcolor="#141A29", border_color="#3498DB", color="white"
                )
                
                lbl_status_profil = ft.Text("", size=12, weight="bold")
                
                def simpan_profil(e):
                    db_config["nama_user"] = inp_nama.value.strip()
                    simpan_pengaturan(db_config)
                    lbl_status_profil.value = f"✅ Nama berhasil disimpan!"
                    lbl_status_profil.color = "#2ECC71"
                    try: page.update()
                    except: pass
                    
                btn_simpan_profil = ft.Container(
                    content=ft.Row([ft.Text("💾 Simpan Nama", color="white", weight="bold")], alignment="center"), 
                    bgcolor="#27AE60", padding=15, border_radius=8, ink=True, on_click=simpan_profil
                )
                
                btn_kembali = ft.Container(content=ft.Row([ft.Text("⬅️ Kembali", color="#BDC3C7", weight="bold")]), padding=10, ink=True, on_click=lambda e: pindah_menu("pengaturan", ""))
                header_profil = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([btn_kembali, ft.Text("Profil Pengguna", weight="bold", size=16, color="white")]))

                form_profil = ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Nama ini akan digabungkan menjadi 'NMC Executive : Nama Anda' di layar Chat Internal.", color="#BDC3C7", size=12),
                        ft.Container(height=15), inp_nama, ft.Container(height=15),
                        btn_simpan_profil,
                        ft.Container(height=5), ft.Row([lbl_status_profil], alignment="center")
                    ])
                )
                area_tengah = ft.Column([header_profil, form_profil], scroll="auto", expand=True)

            elif sub_halaman_aktif == "about":
                btn_kembali = ft.Container(content=ft.Row([ft.Text("⬅️ Kembali", color="#BDC3C7", weight="bold")]), padding=10, ink=True, on_click=lambda e: pindah_menu("pengaturan", ""))
                header_about = ft.Container(bgcolor="#141A29", padding=20, content=ft.Row([btn_kembali, ft.Text("Tentang Aplikasi", weight="bold", size=16, color="white")]))
                
                konten_about = ft.Container(
                    padding=30, 
                    content=ft.Column([
                        ft.Container(height=30), 
                        ft.Image(src="logo.png", width=110, height=110, fit="contain"), 
                        ft.Container(height=15), 
                        ft.Text("NMC EXECUTIVE", weight="bold", size=26, color="white"), 
                        ft.Text("Versi 1.1 (Mobile Edition)", color="#BDC3C7", size=12), 
                        ft.Divider(height=50, color="#2C3E50"), 
                        ft.Text(
                            "Platform monitoring eksekutif untuk memantau dan menganalisis data operasional jembatan timbang secara terpusat dan real-time", 
                            color="#E0E0E0", 
                            text_align="center", 
                            size=13
                        ), 
                        ft.Container(height=50), 
                        
                        # --- FOOTER KONTAK (Dirapatkan dan disamakan warnanya) ---
                        ft.Column([
                            ft.Text("© 2026 PT. Naila Multimedia Center", color="#3498DB", size=12, weight="bold"),
                            ft.Text("Web : https://nmcgroup.web.id", color="#3498DB", size=11, weight="bold"),
                            ft.Text("Kontak : 085656837192 / 081241928332", color="#3498DB", size=11, weight="bold")
                        ], horizontal_alignment="center", spacing=2)
                        
                    ], horizontal_alignment="center")
                )
                
                area_tengah = ft.Column([header_about, konten_about], scroll="auto", expand=True)
                
        # [PENTING UNTUK MOBILE]: Membungkus layar dengan SafeArea agar tidak tertutup Poni HP (Notch)
        page.add(ft.SafeArea(ft.Column([area_tengah, menu_bawah], spacing=0, expand=True), expand=True))
        update_live_ui()

    # ==========================================
    # BYPASS: LANGSUNG MASUK DASHBOARD
    # ==========================================
    threading.Thread(target=robot_penyedot_otomatis, daemon=True).start()
    page.robot_aktif = True
    pindah_menu("dashboard")

# Pastikan baris terakhir ini tetap ada di paling bawah
# Sistem Adaptif Flet Engine
try:
    # Perintah untuk Flet versi terbaru
    ft.run(main) 
except AttributeError:
    # Perintah cadangan untuk Flet versi lama
    ft.app(target=main, assets_dir="assets")
