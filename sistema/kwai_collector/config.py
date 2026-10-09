"""
Configuracao central do kwai_collector. 
Variaveis de ambiente carregadas de um
arquivo `.env` na raiz de sistema/.

Os valores de "fingerprint de dispositivo" (did/egid/zid/session_id/...)
NAO sao credenciais de usuario, sao identificadores de dispositivo
simulado que o app Android manda em toda requisicao, publicos no sentido
de que qualquer instalacao do app gera valores parecidos. Mesmo assim,
ficam configuraveis via .env (nao hardcoded) 
para facilitar trocar de "dispositivo virtual" sem editar codigo.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


# --- Servico local de assinatura __NS_sig3 (ver apk/tools/unidbg) ---
SIG3_SERVICE_URL = _env("SIG3_SERVICE_URL", "http://127.0.0.1:8765")

# --- Endpoints ---
KWAI_WEB_BASE_URL = _env("KWAI_WEB_BASE_URL", "https://www.kwai.com")
KWAI_MOBILE_BASE_URL = _env("KWAI_MOBILE_BASE_URL", "https://api1-us.kwai-pro.com")

# --- Timeouts / paginacao ---
HTTP_TIMEOUT_SECONDS = _env_int("HTTP_TIMEOUT_SECONDS", 20)
SEARCH_PAGE_SIZE = _env_int("SEARCH_PAGE_SIZE", 10)
COMMENTS_PAGE_SIZE = _env_int("COMMENTS_PAGE_SIZE", 20)
MEDIA_DOWNLOAD_DELAY_SECONDS = _env_int("MEDIA_DOWNLOAD_DELAY_SECONDS", 1)

# --- User-Agents ---
WEB_USER_AGENT = _env(
    "WEB_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
MOBILE_USER_AGENT = _env("MOBILE_USER_AGENT", "kwai-android")

# --- Fingerprint de dispositivo simulado (app mobile) ---
# Valores-padrao vieram de capturas reais ja validadas nesta pesquisa
# (ver PESQUISA.md); nenhum deles e uma credencial de conta/usuario.
DEVICE = {
    "abi": _env("DEVICE_ABI", "arm64"),
    "app": _env("DEVICE_APP", "1"),
    "appver": _env("DEVICE_APPVER", "10.3.20.539600"),
    "ver": _env("DEVICE_VER", "10.3"),
    "sys": _env("DEVICE_SYS", "KWAI_ANDROID_17"),
    "mod": _env("DEVICE_MOD", "Google(sdk_gphone64_x86_64)"),
    "c": _env("DEVICE_C", "GOOGLE_PLAY"),
    "client_key": _env("DEVICE_CLIENT_KEY", "3c2cd3f3"),
    "kpn": _env("DEVICE_KPN", "KWAI"),
    "kpf": _env("DEVICE_KPF", "ANDROID_PHONE"),
    "pkg": _env("DEVICE_PKG", "kwai.lite.video"),
    "net": _env("DEVICE_NET", "WIFI"),
    "mcc": _env("DEVICE_MCC", "310"),
    "country_code": _env("DEVICE_COUNTRY_CODE", "us"),
    "countryInfo": _env("DEVICE_COUNTRY_INFO", "USA"),
    "bucket": _env("DEVICE_BUCKET", "usa"),
    "language": _env("DEVICE_LANGUAGE", "en-us"),
    "did": _env("DEVICE_DID", "ANDROID_49bc4eda990d0da8"),
    "vid": _env("DEVICE_VID", "ANDROID_49bc4eda990d0da8"),
    "egid": _env(
        "DEVICE_EGID",
        "DFP16BE49C6E55C4EF3A67E008DD0B5B1328E15B0351CA3FAC98698F31E7046E",
    ),
    "zid": _env("DEVICE_ZID", "Z10676064657"),
    "session_id": _env("DEVICE_SESSION_ID", "94e862a2-85df-428d-8f1e-125e6e4416b6"),
    "app_id": _env("DEVICE_APP_ID", "8e58d8f8-0d73-44d8-807d-d03ddd523804"),
    "user_id": _env("DEVICE_USER_ID", "150001752655214"),
    "ad_ext_info": _env(
        "DEVICE_AD_EXT_INFO",
        '{"gaid":"c5473c6a-a40d-4f3a-84fb-e992767daeab",'
        '"userAgent":"Dalvik/2.1.0 (Linux; U; Android 17; '
        'sdk_gphone64_x86_64 Build/CE2A.260420.019)"}',
    ),
    "time_zone": _env("DEVICE_TIME_ZONE", "GMT GMT"),
}
