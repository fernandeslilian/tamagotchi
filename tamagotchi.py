import csv
import json
import os
import random
import time
from datetime import datetime
import paho.mqtt.client as mqtt

# --- CONFIGURACOES DE REDE MQTT ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

TOPICO_SENSORES = "tamagotchi/iot/sensores"
TOPICO_TELA = "tamagotchi/iot/tela"
TOPICO_STATUS = "tamagotchi/iot/status"

ARQUIVO_CSV = "telemetria_rede.csv"

# --- BANCO DE FALAS DA MAQUINA DE ESTADOS ---
# Textos sem acentos e ate 18 caracteres para caber no Display OLED
FALAS_POR_ESTADO = {
    "CALOR": [
        "Que calor! Agua!",
        "To derretendo!",
        "Liga o ventilador!"
    ],
    "FRIO": [
        "Brrr! Que frio!",
        "Cade meu casaco?",
        "Congelando aqui!"
    ],
    "ESTUDANDO": [
        "Modo foco total!",
        "Bora estudar!",
        "Foco no projeto!"
    ],
    "DORMINDO": [
        "Zzz... cade voce?",
        "Tirando cochilo...",
        "Modo economia Zzz"
    ],
    "FELIZ": ["Oba! Voce voltou!", "Que bom te ver!", "Miau! Que alegria!"],
    "TRISTE": ["To com saudade...", "Volta logo!", "Cade voce?"],
    "ASSUSTADO": ["Aaa! Que susto!", "O que foi isso?!", "Me assustei!"],
    "BRAVO": ["Me da espaco!", "Muito pertinho!", "Sai um pouquinho!"],
    "CARINHOSO": ["Gosto de voce!", "Fica comigo!", "Ronron... <3"],
    "NORMAL": [
        "Tudo tranquilo!",
        "Rede MQTT 100%!",
        "Dia produtivo!"
    ]
}

# Variaveis de controle de trafego na rede
ultimo_estado_enviado = None
contador_pacotes = 0

# Controles temporais da FSM (monotonic evita saltos no relogio do PC).
ultima_distancia = None
inicio_longe = None
inicio_muito_perto = None
inicio_carinho = None
estado_evento = None
fim_evento = 0.0

TEMPO_BRAVO = 5.0
TEMPO_CARINHO = 10.0
TEMPO_TRISTE = 60.0
TEMPO_EVENTO = 6.0


def inicializar_csv():
    """Cria o arquivo CSV com cabecalho caso ainda nao exista."""
    if not os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "tamanho_payload_bytes",
                "temperatura_c",
                "umidade_pct",
                "distancia_cm",
                "estado_fsm"
            ])


def registrar_no_csv(tamanho_bytes, temp, umid, dist, estado):
    """Salva cada pacote recebido para gerar graficos."""
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ARQUIVO_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([agora, tamanho_bytes, temp, umid, dist, estado])


def avaliar_maquina_de_estados(temp, umid, dist, agora=None):
    """FSM com temporizadores e eventos, avaliada a cada telemetria (~3 s).

    Prioridade: temperatura -> evento breve -> proximidade mantida -> ausencia
    -> estudando -> normal. BRAVO, CARINHOSO e TRISTE requerem permanencia.
    """
    global ultima_distancia, inicio_longe, inicio_muito_perto
    global inicio_carinho, estado_evento, fim_evento

    if agora is None:
        agora = time.monotonic()

    # Atualiza os temporizadores mesmo enquanto algum evento estiver ativo.
    if dist > 200:
        if inicio_longe is None:
            inicio_longe = agora
    else:
        inicio_longe = None

    if dist < 10:
        if inicio_muito_perto is None:
            inicio_muito_perto = agora
    else:
        inicio_muito_perto = None

    if 10 <= dist < 30:
        if inicio_carinho is None:
            inicio_carinho = agora
    else:
        inicio_carinho = None

    # Transicoes discretas: verifica uma unica vez por nova leitura.
    voltou = ultima_distancia is not None and ultima_distancia > 200 and dist <= 80
    susto = (ultima_distancia is not None and
             ultima_distancia - dist > 50 and not voltou)
    ultima_distancia = dist

    # Temperaturas extremas tem prioridade e nao retêm reacoes pendentes.
    if temp > 30.0:
        estado_evento = None
        return "CALOR"
    if temp < 18.0:
        estado_evento = None
        return "FRIO"

    # FELIZ e ASSUSTADO ficam na tela por ~6 segundos para serem percebidos.
    if voltou:
        estado_evento, fim_evento = "FELIZ", agora + TEMPO_EVENTO
    elif susto:
        estado_evento, fim_evento = "ASSUSTADO", agora + TEMPO_EVENTO
    if estado_evento is not None:
        if agora < fim_evento:
            return estado_evento
        estado_evento = None

    if inicio_muito_perto is not None and agora - inicio_muito_perto >= TEMPO_BRAVO:
        return "BRAVO"
    if inicio_carinho is not None and agora - inicio_carinho >= TEMPO_CARINHO:
        return "CARINHOSO"
    if inicio_longe is not None:
        if agora - inicio_longe >= TEMPO_TRISTE:
            return "TRISTE"
        return "DORMINDO"
    if dist < 40:
        return "ESTUDANDO"
    return "NORMAL"


# --- CALLBACKS DE REDE MQTT ---
def on_connect(client, userdata, flags, rc, *args):
    if rc == 0:
        print("=" * 60)
        print(f"[SERVIDOR] Conectado ao Broker {MQTT_BROKER}:{MQTT_PORT}")
        print(f"[SERVIDOR] Escutando telemetria em: {TOPICO_SENSORES}")
        print(f"[SERVIDOR] Monitorando status em: {TOPICO_STATUS}")
        print("=" * 60)
        client.subscribe([(TOPICO_SENSORES, 0), (TOPICO_STATUS, 1)])
    else:
        print(f"[ERRO] Falha na conexao com o Broker. Codigo: {rc}")


def on_message(client, userdata, msg):
    global ultimo_estado_enviado, contador_pacotes

    topico = msg.topic
    payload_bruto = msg.payload.decode("utf-8", errors="ignore")
    tamanho_bytes = len(msg.payload)

    # Mensagem de Status / Last Will and Testament (LWT)
    if topico == TOPICO_STATUS:
        print(f"\n[STATUS DO NO IoT] Topico: {topico} | Payload: {payload_bruto}")
        return

    # Telemetria dos sensores
    if topico == TOPICO_SENSORES:
        try:
            dados = json.loads(payload_bruto)
            temp = float(dados.get("temp", 24.0))
            umid = float(dados.get("umid", 50.0))
            dist = int(dados.get("dist", 80))
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            print(f"[ERRO] Pacote JSON malformado: {payload_bruto} ({e})")
            return

        contador_pacotes += 1
        novo_estado = avaliar_maquina_de_estados(temp, umid, dist)
        registrar_no_csv(tamanho_bytes, temp, umid, dist, novo_estado)

        print(
            f"[UPLINK #{contador_pacotes:03d}] {tamanho_bytes} bytes | "
            f"Temp: {temp:.1f}C | Umid: {umid:.0f}% | Dist: {dist}cm -> Estado: {novo_estado}"
        )

        # Envia atualizacao ao display quando o estado muda ou a cada 5 pacotes
        if novo_estado != ultimo_estado_enviado or contador_pacotes % 5 == 0:
            fala_sorteada = random.choice(FALAS_POR_ESTADO[novo_estado])
            comando_downlink = {
                "estado": novo_estado,
                "fala": fala_sorteada
            }
            payload_resposta = json.dumps(comando_downlink)
            client.publish(TOPICO_TELA, payload_resposta, qos=1)
            ultimo_estado_enviado = novo_estado

            print(
                f"   └── [DOWNLINK ENVIADO] Topico: {TOPICO_TELA} (QoS 1) | "
                f"Payload ({len(payload_resposta)} bytes): {payload_resposta}"
            )


def iniciar_servidor():
    inicializar_csv()

    # Compatibilidade com paho-mqtt 1.x e 2.x
    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="Servidor-Python-FSM"
        )
    except AttributeError:
        client = mqtt.Client(client_id="Servidor-Python-FSM")

    client.on_connect = on_connect
    client.on_message = on_message

    print("[REDE] Iniciando conexao com o Broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando conexao MQTT...")
        client.disconnect()


if __name__ == "__main__":
    iniciar_servidor()
