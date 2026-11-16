import network, time, json, gc
import urequests as requests
from machine import Pin, I2C
import ssd1306

led = Pin(2, Pin.OUT)

i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
print("I2C:", [hex(a) for a in i2c.scan()])
oled = ssd1306.SSD1306_I2C(128, 64, i2c, 0x3C)

LARGURA = 16
LINHAS_TEXTO = 7
ATRASO_PAGINA = 7

_DE   = "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ"
_PARA = "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN"
SUBST = {}
for _a, _b in zip(_DE, _PARA):
    SUBST[_a] = _b
SUBST.update({"’": "'", "‘": "'", "“": '"', "”": '"',
              "–": "-", "—": "-", "…": "...", "•": "*",
              "«": '"', "»": '"'})

def normalizar(texto):
    saida = []
    for c in texto:
        c = SUBST.get(c, c)
        if c in "\r\n\t":
            c = " "
        saida.append(c if all(32 <= ord(x) < 127 for x in c) else " ")
    return "".join(saida)

def quebrar_linhas(texto, largura=LARGURA):
    linhas = []
    atual = ""
    for palavra in texto.split():
        while len(palavra) > largura:
            if atual:
                linhas.append(atual)
                atual = ""
            linhas.append(palavra[:largura])
            palavra = palavra[largura:]
        if not atual:
            atual = palavra
        elif len(atual) + 1 + len(palavra) <= largura:
            atual += " " + palavra
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas

def mostrar_status(titulo, detalhe=""):
    oled.fill(0)
    oled.text(titulo[:LARGURA], 0, 0)
    y = 16
    for linha in quebrar_linhas(normalizar(detalhe))[:5]:
        oled.text(linha, 0, y)
        y += 8
    oled.show()

def mostrar_paginas(texto):
    linhas = quebrar_linhas(normalizar(texto))
    paginas = [linhas[i:i + LINHAS_TEXTO]
               for i in range(0, len(linhas), LINHAS_TEXTO)] or [[]]
    total = len(paginas)
    for n, pag in enumerate(paginas, 1):
        oled.fill(0)
        for i, linha in enumerate(pag):
            oled.text(linha, 0, i * 8)
        if total > 1:
            oled.text("%d/%d" % (n, total), 0, 56)
        oled.show()
        if n < total:
            time.sleep(ATRASO_PAGINA)

PROVEDOR = "openrouter"
API_KEY = "CHAVE-API-AQUI"

PROVEDORES = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions",
                   "inclusionai/ling-3.2-flash:free"),
    "deepseek":   ("https://api.deepseek.com/chat/completions",
                   "deepseek-chat"),
}
URL, MODELO = PROVEDORES[PROVEDOR]

historico = [{
    "role": "system",
    "content": "Você é um assistente embarcado em um ESP32. "
               "Responda em português. Evite o uso de markdowns. Mantenha as respostas curta e concisas o suficiente para encaixar no maximo 3 paginas em uma tela de 128px",
}]

def conectar_wifi():
    mostrar_status("Conectando")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect("Wokwi-GUEST", "")
    print("Conectando ao internet", end="")
    for _ in range(150):
        if wlan.isconnected():
            print("\nConectado!")
            mostrar_status("Conexao OK", wlan.ifconfig()[0])
            return
        print(".", end="")
        time.sleep(0.2)
    mostrar_status("Erro ao conectar")
    raise RuntimeError("Erro ao conectar!")

def perguntar(texto):
    historico.append({"role": "user", "content": texto})
    corpo = json.dumps({
        "model": MODELO,
        "messages": historico,
        "reasoning": {"enabled": False},
    })
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + API_KEY,
    }
    led.on()
    try:
        r = requests.post(URL, data=corpo.encode("utf-8"), headers=headers)
        if r.status_code != 200:
            erro = "Erro HTTP %d: %s" % (r.status_code, r.text[:200])
            r.close()
            historico.pop()
            return erro
        msg = r.json()["choices"][0]["message"]
        resposta = (msg.get("content") or "").strip()
        r.close()
        if not resposta:
            historico.pop()
            return "Resposta vazia. Tente novamente."
    except Exception as e:
        historico.pop()
        return "Falha na requisição: %s" % e
    finally:
        led.off()
        gc.collect()

    historico.append({"role": "assistant", "content": resposta})
    if len(historico) > 7:
        del historico[1:3]
    return resposta

conectar_wifi()
print("Assistente conectado.\nProvedor: %s\nModelo: %s\n" % (PROVEDOR, MODELO))
mostrar_status("Pronto!", "Digite no monitor serial")

while True:
    try:
        pergunta = input("Você> ").strip()
    except KeyboardInterrupt:
        break
    if pergunta:
        mostrar_status("Pensando...", pergunta)
        resposta = perguntar(pergunta)
        print("IA> " + resposta + "\n")
        mostrar_paginas(resposta)