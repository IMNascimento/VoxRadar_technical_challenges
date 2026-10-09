"""
Reconstrucao em Python puro do campo `sig` (corpo do form) usado por
/rest/o/comment/list/v2 e outras rotas do Kwai que passam por
Lcw/u;->z(...) -> CPU.a() -> libcore.so::getClock.

Algoritmo reconstruido via engenharia reversa estatica com Ghidra,
documentado em PESQUISA.md.
"""
import hashlib
import struct
from pathlib import Path

_ASM_DIR = Path(__file__).parent / "asm"


def _rotl32(x: int, n: int) -> int:
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _rotr32(x: int, n: int) -> int:
    x &= 0xFFFFFFFF
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


class _KeyDeriver:
    """Porta em Python da cifra customizada encontrada em libcore.so
    (dentro de CPU.getClock) que deriva um valor fixo de 16 bytes a
    partir apenas de constantes embutidas no binario (S-box + tabela de
    permutacao + 4 palavras de IV, 8 rounds)."""

    def __init__(self):
        self.buf14 = list(struct.unpack("<8I", (_ASM_DIR / "buf14.bin").read_bytes()))
        self.H = (_ASM_DIR / "hsbox.bin").read_bytes()
        self.KI = list(struct.unpack("<56I", (_ASM_DIR / "keyindex_pos.bin").read_bytes()))

    def _hsub(self, x: int) -> int:
        x &= 0xFFFFFFFF
        H = self.H
        return (H[(x >> 24) & 0xFF] << 24) | (H[(x >> 16) & 0xFF] << 16) | (H[(x >> 8) & 0xFF] << 8) | H[x & 0xFF]

    def derive(self, iv18: int, iv20: int, iv21: int, iv19: int) -> bytes:
        buf14, KI, hsub = self.buf14, self.KI, self._hsub
        uVar18, uVar20, uVar21, uVar19 = iv18, iv20, iv21, iv19
        pos = 55
        rounds = 8
        while rounds != 0:
            i0, i1, i2, i3, i4, i5, i6 = (
                KI[pos], KI[pos - 1], KI[pos - 2], KI[pos - 3], KI[pos - 4], KI[pos - 5], KI[pos - 6],
            )
            uVar2 = (buf14[i0] + uVar19) & 0xFFFFFFFF
            uVar3 = (buf14[i1] + uVar18) & 0xFFFFFFFF
            uVar3 = hsub(uVar3)
            uVar2 = uVar21 ^ _rotl32(hsub(uVar2), 5)
            uVar20 = uVar20 ^ _rotr32(uVar3, 0xB)
            uVar21 = (uVar20 + uVar2 + buf14[i3]) & 0xFFFFFFFF
            uVar21 = hsub(uVar21)
            uVar3 = (rounds ^ _rotr32(uVar21, 0xB)) & 0xFFFFFFFF
            uVar21 = (buf14[i2] + uVar2) & 0xFFFFFFFF
            rounds -= 1
            uVar5 = (uVar20 - uVar3) & 0xFFFFFFFF
            uVar20 = (uVar5 + buf14[i4]) & 0xFFFFFFFF
            uVar21 = hsub(uVar21)
            uVar20 = hsub(uVar20)
            uVar21 = (uVar19 - _rotr32(uVar21, 0x13)) & 0xFFFFFFFF
            pos -= 7
            uVar20 = (_rotr32(uVar20, 0x13) + uVar18) & 0xFFFFFFFF
            uVar18 = (buf14[i5] + uVar21) & 0xFFFFFFFF
            uVar19 = (buf14[i6] + uVar20) & 0xFFFFFFFF
            uVar18 = hsub(uVar18)
            uVar18 = ((uVar3 + uVar2) ^ _rotr32(uVar18, 0xB)) & 0xFFFFFFFF
            uVar19 = uVar5 ^ _rotl32(hsub(uVar19), 5)
        return struct.pack("<4I", uVar20 & 0xFFFFFFFF, uVar19 & 0xFFFFFFFF, uVar18 & 0xFFFFFFFF, uVar21 & 0xFFFFFFFF)


_deriver = None


def _get_deriver() -> _KeyDeriver:
    global _deriver
    if _deriver is None:
        _deriver = _KeyDeriver()
    return _deriver


def _trim_cstring(b: bytes) -> bytes:
    nul = b.find(b"\x00")
    return b[:16] if nul == -1 else b[:nul]


# IVs (uVar18, uVar20, uVar21, uVar19) observados no smali/decompilado.
# "warm" = chamadas subsequentes na mesma sessao (cpu_inited != 0).
# "cold" = primeira chamada apos carregar a lib (decodifica como o literal
#          "com.kwai.video", o package name do app).
WARM_IV = (0xC90F998F, 0x45394E1E, 0x5E9D9B67, 0x39B692AA)
COLD_IV = (0x6F4FD2C7, 0x8A97E931, 0x470BF4AF, 0x56204052)


def get_key(warm: bool = True) -> bytes:
    """Retorna a chave (ja truncada em byte nulo, como o app faz) usada
    como sufixo do MD5. E uma constante fixa do binario -- nao depende
    de sessao/dispositivo -- mas o app usa uma chave diferente na
    primeira chamada ("cold") vs chamadas seguintes ("warm")."""
    iv = WARM_IV if warm else COLD_IV
    raw = _get_deriver().derive(*iv)
    return _trim_cstring(raw)


def build_sig_input(params: dict) -> bytes:
    """params = urlParams + bodyParams (SEM __NS_sig3/__NS_sig4/sig/
    __NStokensig -- esses sao adicionados depois ou dependem do sig)."""
    pairs = sorted(f"{k}={v}" for k, v in params.items())
    return "".join(pairs).encode("utf-8")


def resign(query: dict, body: dict, warm: bool = True) -> str:
    """Recalcula o `sig` para um par (query, body) reais de uma requisicao
    /rest/o/comment/list/v2 (ou similar). `query`/`body` podem incluir os
    campos de saida (__NS_sig3/__NS_sig4/sig/client_key/__NStokensig) --
    eles sao removidos automaticamente antes do calculo, e `client_key` e
    reinserido (ele participa do hash, so nao e um dos "outputs" dele)."""
    client_key = body.get("client_key", "3c2cd3f3")
    body_clean = {k: v for k, v in body.items() if k not in ("sig", "client_key")}
    body_clean["client_key"] = client_key
    query_clean = {
        k: v for k, v in query.items()
        if k not in ("__NS_sig3", "__NS_sig4", "__NStokensig")
    }
    return compute_sig({**query_clean, **body_clean}, warm=warm)


def compute_sig(params: dict, warm: bool = True) -> str:
    sig_input = build_sig_input(params)
    key = get_key(warm=warm)
    return hashlib.md5(sig_input + key).hexdigest()
