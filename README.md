# 🐱 Gatinho Virtual

Projeto de um Tamagotchi virtual desenvolvido com **ESP32, Python e protocolo MQTT**, utilizando sensores para simular diferentes estados emocionais de um gatinho a partir da interação com ele.

## Tecnologias utilizadas

- ESP32
- Python
- C++ (Arduino)
- MQTT — HiveMQ Broker
- Wokwi
- Display OLED SSD1306 (128×64)
- Sensor DHT22 (temperatura e umidade)
- Sensor ultrassônico HC-SR04

## Funcionalidades

O Tamagotchi apresenta diferentes expressões faciais de acordo com as informações recebidas dos sensores.

**Estados implementados:**

| Estado | Comportamento |
|---|---|
| NORMAL | Gatinho tranquilo |
| FELIZ | Reage à aproximação |
| TRISTE | Reage à ausência prolongada |
| ASSUSTADO | Reage a uma aproximação repentina |
| BRAVO | Reage à proximidade excessiva |
| CARINHOSO | Reage à presença próxima |
| CALOR | Temperatura elevada |
| FRIO | Temperatura baixa |
| ESTUDANDO | Detecta uma distância específica |
| DORMINDO | Ausência de interação |

Cada estado possui uma expressão facial em pixel art exibida no display OLED.

## Funcionamento

A comunicação entre o ESP32 e o Python ocorre por meio do protocolo MQTT, utilizando o modelo Publish/Subscribe.

1. O ESP32 coleta os dados dos sensores.
2. As informações são publicadas em um broker MQTT.
3. O Python recebe os dados e processa a máquina de estados.
4. O estado emocional e uma mensagem são enviados ao ESP32.
5. O display OLED atualiza a expressão facial do gatinho.

O sistema também registra dados de telemetria em um arquivo CSV para análise.

## Como executar

**1. ESP32**

Abra o arquivo `sketch.ino` no Wokwi e inicie a simulação.

**2. Python**

Instale a biblioteca necessária:

```bash
pip install paho-mqtt
```

Execute o programa:

```bash
python tamagotchi.py
```

**3. Comunicação MQTT**

Com o ESP32 e o Python conectados ao broker MQTT, o gatinho começará a reagir automaticamente às alterações dos sensores.
