"""Maska osoby pro efekt „text za hlavou“.

Pro každý snímek reelu (1080x1920) spočítá, kde je osoba (255) a kde pozadí (0).
Model: MediaPipe Selfie Segmenter (Google, Apache 2.0, 250 kB), běží přes ai-edge-litert,
jen na CPU, všechno místně. Video se nikam neposílá.

Postup:
1. ffmpeg dekóduje video rovnou zmenšené na 270x480 (4x menší než reel) do roury.
2. Každý snímek se zmenší na 256x256, model vrátí pravděpodobnost osoby 0..1.
3. Klouzavý průměr přes 3 snímky, ať okraj nebliká.
4. Maska se uloží jako uint8 270x480 do souboru .npy (memmap, pro 120 s reel ~470 MB).
5. Při čtení se maska zvětší na 1080x1920 (bilineárně) a okraj se změkčí Gaussovým rozmazáním.

Když cache existuje a sedí na video, nic se nepočítá.
Potřebuje: numpy, opencv-python-headless, ai-edge-litert, ffmpeg a ffprobe v PATH.
"""
import os
import subprocess
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .cesty import koren_balicku

MODEL = koren_balicku() / "modely" / "selfie_segmenter.tflite"
VELIKOST_MODELU_B = 249537                # OVĚŘENO 19. 10. 2026 (karta modelu, stažený soubor)
SIRKA, VYSKA = 1080, 1920                 # rozměr reelu
SIRKA_M, VYSKA_M = 270, 480               # rozměr uložené masky (4x menší)
OKNO_PRUMERU = 3                          # klouzavý průměr přes tolik snímků
ROZMAZANI_PX = 3                          # změkčení okraje při zvětšení
MEZIPAMET = 8                             # kolik posledních zvětšených masek si pamatovat
BAJTU_NA_SNIMEK = SIRKA_M * VYSKA_M * 3   # rgb24 ze ffmpeg


def chyba_dostupnosti():
    """Vrátí None, když maska půjde spočítat, jinak českou větu, co chybí."""
    try:
        from ai_edge_litert.interpreter import Interpreter  # noqa: F401
    except ImportError:
        return "Chybí balíček ai-edge-litert: nainstaluj ho příkazem uv pip install ai-edge-litert==2.3.0."
    if not MODEL.is_file():
        return "Chybí model selfie_segmenter.tflite, má být v %s." % MODEL
    return None


def k_dispozici():
    """True, když jde importovat ai_edge_litert a existuje model."""
    return chyba_dostupnosti() is None


def nacti_model():
    """Načte LiteRT interpreter. Vrátí (interpreter, index vstupu, index výstupu, (výška, šířka) vstupu)."""
    chyba = chyba_dostupnosti()
    if chyba:
        raise RuntimeError(chyba)
    from ai_edge_litert.interpreter import Interpreter
    vlaken = max(1, min(4, os.cpu_count() or 1))
    it = Interpreter(model_path=str(MODEL), num_threads=vlaken)
    it.allocate_tensors()
    vstup, vystup = it.get_input_details()[0], it.get_output_details()[0]
    tvar = [int(x) for x in vstup["shape"]]
    if len(tvar) != 4 or tvar[3] != 3:
        raise RuntimeError("Model selfie_segmenter.tflite má nečekaný vstup %s, čekám 1x256x256x3." % tvar)
    return it, vstup["index"], vystup["index"], (tvar[1], tvar[2])


def _udaje_videa(video):
    """Počet snímků a délka videa podle ffprobe (nic se nedekóduje). Vrátí (snímků nebo None, sekund nebo None)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_frames,duration:format=duration", "-of", "default=nw=1",
                              str(video)], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise RuntimeError("Nenašel jsem ffprobe, nainstaluj ffmpeg (na Macu brew install ffmpeg).")
    except subprocess.CalledProcessError:
        raise RuntimeError("Video %s se nepodařilo přečíst (ffprobe)." % video)
    snimku, delka = None, None
    for radek in out.splitlines():
        klic, _, hodnota = radek.partition("=")
        hodnota = hodnota.strip()
        if klic == "nb_frames" and hodnota.isdigit():
            snimku = int(hodnota)
        elif klic == "duration" and delka is None:
            try:
                delka = float(hodnota)
            except ValueError:
                pass
    return snimku, delka


class Maska:
    """Maska osoby pro každý snímek videa. maska[i] je uint8 (1920, 1080), 255 = osoba.

    video: MP4 1080x1920 (už sestříhaný základ reelu bez textu)
    cache: soubor .npy, kam se masky uloží (memmap uint8 tvaru (N, 480, 270))
    fps: snímkovost reelu, index snímku = round(t * fps)
    """

    def __init__(self, video, cache, fps=30):
        self.video = Path(video)
        self.cache = Path(cache)
        self.fps = float(fps)
        self._data = None
        self._mezipamet = OrderedDict()
        if not self.video.is_file():
            raise FileNotFoundError("Video %s neexistuje." % self.video)
        self.ocekavano, self.delka_s = _udaje_videa(self.video)
        if self.ocekavano is None and self.delka_s is not None:
            self.ocekavano = int(round(self.delka_s * self.fps))
        self._nacti_cache()

    # --- cache -----------------------------------------------------------------

    def _nacti_cache(self):
        """Otevře cache, když existuje, má správný tvar, správný počet snímků a je novější než video."""
        if not self.cache.is_file():
            return False
        try:
            data = np.load(str(self.cache), mmap_mode="r")
        except (ValueError, OSError):
            return False
        if data.ndim != 3 or data.shape[1:] != (VYSKA_M, SIRKA_M) or data.dtype != np.uint8 or len(data) == 0:
            return False
        if self.ocekavano is not None and abs(len(data) - self.ocekavano) > 2:
            return False
        if self.cache.stat().st_mtime < self.video.stat().st_mtime:
            return False
        self._data = data
        return True

    @property
    def hotovo(self):
        """True, když jsou masky spočítané (v paměti z cache nebo po spocitej)."""
        return self._data is not None

    def __len__(self):
        return 0 if self._data is None else len(self._data)

    # --- výpočet ---------------------------------------------------------------

    def _snimky(self):
        """Dekóduje video přes ffmpeg do roury, po snímcích 270x480 rgb24 (numpy uint8 (480, 270, 3))."""
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(self.video),
               "-vf", "fps=%g,scale=%d:%d:flags=area" % (self.fps, SIRKA_M, VYSKA_M),
               "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise RuntimeError("Nenašel jsem ffmpeg, nainstaluj ho (na Macu brew install ffmpeg).")
        try:
            while True:
                buf = p.stdout.read(BAJTU_NA_SNIMEK)
                if len(buf) < BAJTU_NA_SNIMEK:
                    break
                yield np.frombuffer(buf, np.uint8).reshape(VYSKA_M, SIRKA_M, 3)
        finally:
            p.stdout.close()
            chyby = p.stderr.read().decode("utf-8", "replace").strip()
            p.stderr.close()
            p.wait()
        if p.returncode != 0:
            raise RuntimeError("ffmpeg nedokázal přečíst video %s: %s" % (self.video.name, chyby[:200]))

    def spocitej(self, hlaseni=None):
        """Projde celé video a uloží masky do cache. hlaseni(text) dostane postup po 10 %.

        Vrátí počet snímků. Když cache už sedí, nic nepočítá.
        """
        import cv2
        if self._data is not None:
            return len(self._data)
        it, i_vstup, i_vystup, (vys, sir) = nacti_model()
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        docasny = self.cache.with_name(self.cache.name + ".tmp")
        odhad = self.ocekavano or 1
        dalsi_hlaseni = 10
        pocet = 0
        fronta = []                         # pravděpodobnosti 256x256 čekající na klouzavý průměr
        zapsano = 0

        def uloz(soubor, prumer):
            m = cv2.resize((np.clip(prumer, 0, 1) * 255).astype(np.uint8), (SIRKA_M, VYSKA_M),
                           interpolation=cv2.INTER_LINEAR)
            soubor.write(np.ascontiguousarray(m).tobytes())

        with open(docasny, "wb") as f:
            # hlavička .npy s odhadem počtu snímků; po dokončení se přepíše skutečným počtem
            delka_hlavicky = self._zapis_hlavicku(f, odhad)
            for snimek in self._snimky():
                x = cv2.resize(snimek, (sir, vys), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                it.set_tensor(i_vstup, x[None])
                it.invoke()
                y = it.get_tensor(i_vystup)[0]
                y = y[..., -1] if y.ndim == 3 else y          # poslední kanál = osoba
                fronta.append(np.array(y, np.float32))
                pocet += 1
                # klouzavý průměr: snímek j zapisujeme, až známe j+1
                if len(fronta) == 2:
                    uloz(f, (fronta[0] + fronta[1]) / 2)        # první snímek: průměr se sousedem
                    zapsano += 1
                elif len(fronta) == OKNO_PRUMERU:
                    uloz(f, sum(fronta) / OKNO_PRUMERU)
                    zapsano += 1
                    fronta.pop(0)
                if hlaseni and self.ocekavano and pocet * 100 >= dalsi_hlaseni * odhad and dalsi_hlaseni < 100:
                    hlaseni("Maska osoby: %d %% (%d z %d snímků)" % (dalsi_hlaseni, pocet, odhad))
                    dalsi_hlaseni += 10
            # dopsat zbytek fronty
            if pocet == 1:
                uloz(f, fronta[0])
                zapsano += 1
            elif len(fronta) == 2:
                uloz(f, (fronta[0] + fronta[1]) / 2)             # poslední snímek: průměr se sousedem
                zapsano += 1
            if zapsano == 0:
                raise RuntimeError("Video %s nemá žádné snímky." % self.video.name)
            f.seek(0)
            if self._zapis_hlavicku(f, zapsano) != delka_hlavicky:
                raise RuntimeError("Hlavička cache masky má jinou délku, než se čekalo (%d snímků)." % zapsano)
        if self.cache.exists():
            self.cache.unlink()
        docasny.replace(self.cache)
        if hlaseni:
            hlaseni("Maska osoby: 100 %% (%d snímků), uloženo do %s" % (zapsano, self.cache.name))
        self._data = np.load(str(self.cache), mmap_mode="r")
        self._mezipamet.clear()
        return zapsano

    @staticmethod
    def _zapis_hlavicku(f, pocet):
        """Zapíše hlavičku formátu .npy pro pole uint8 (pocet, 480, 270). Vrátí její délku v bajtech."""
        zacatek = f.tell()
        np.lib.format.write_array_header_1_0(
            f, {"descr": "|u1", "fortran_order": False, "shape": (int(pocet), VYSKA_M, SIRKA_M)})
        return f.tell() - zacatek

    # --- čtení -----------------------------------------------------------------

    def _vyzaduj(self):
        if self._data is None:
            raise RuntimeError("Maska ještě není spočítaná, zavolej spocitej().")

    def mala(self, i):
        """Maska snímku i v uloženém rozlišení (480, 270), uint8. Mimo rozsah vrátí první nebo poslední snímek."""
        self._vyzaduj()
        i = min(max(int(i), 0), len(self._data) - 1)
        return self._data[i]

    def __getitem__(self, i):
        """Maska snímku i jako uint8 (1920, 1080), 255 = osoba, okraj změkčený."""
        import cv2
        self._vyzaduj()
        i = min(max(int(i), 0), len(self._data) - 1)
        m = self._mezipamet.get(i)
        if m is not None:
            self._mezipamet.move_to_end(i)
            return m
        m = cv2.resize(np.asarray(self._data[i]), (SIRKA, VYSKA), interpolation=cv2.INTER_LINEAR)
        m = cv2.GaussianBlur(m, (0, 0), ROZMAZANI_PX)
        self._mezipamet[i] = m
        while len(self._mezipamet) > MEZIPAMET:
            self._mezipamet.popitem(last=False)
        return m

    def maska_v_case(self, t):
        """Maska pro čas t v sekundách (index = round(t * fps))."""
        return self[int(round(float(t) * self.fps))]

    def podil_osoby(self):
        """Průměrný podíl plochy osoby 0..1 (vzorek každého 10. snímku). Pod 0,1 nebo nad 0,8 je maska podezřelá."""
        self._vyzaduj()
        return float(np.asarray(self._data[::10]).mean() / 255.0)
