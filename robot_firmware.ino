#include <LiquidCrystal_I2C.h>
#include <Wire.h>
#include <driver/i2s.h>

#define I2S_WS 15
#define I2S_SD 32
#define I2S_SCK 14
#define I2S_PORT I2S_NUM_0
#define BUZZER_PIN 4
#define POT_PIN 34

LiquidCrystal_I2C lcd(0x27, 16, 2);

#define SAMPLE_RATE 16000
#define BUFFER_LEN 512
#define DEFAULT_THRESHOLD 4000
#define SILENCE_DURATION 1200
#define PRE_BUF_SIZE 4000

int16_t preBuffer[PRE_BUF_SIZE];
volatile int preBufferHead = 0;
volatile bool isRecording = false;
volatile int32_t currentVolume = 0;
volatile int32_t soundThreshold = DEFAULT_THRESHOLD;
TaskHandle_t Task1;

byte bar1[8] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F};
byte bar2[8] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x1F};
byte bar3[8] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x1F, 0x1F};
byte bar4[8] = {0x00, 0x00, 0x00, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F};
byte bar5[8] = {0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F};

void setup() {
  Serial.begin(921600);

  lcd.init();
  lcd.backlight();
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(POT_PIN, INPUT);
  digitalWrite(BUZZER_PIN, HIGH);

  lcd.createChar(0, bar1);
  lcd.createChar(1, bar2);
  lcd.createChar(2, bar3);
  lcd.createChar(3, bar4);
  lcd.createChar(4, bar5);

  const i2s_config_t i2s_config = {
      .mode = i2s_mode_t(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format =
          i2s_comm_format_t(I2S_COMM_FORMAT_I2S | I2S_COMM_FORMAT_I2S_MSB),
      .intr_alloc_flags = 0,
      .dma_buf_count = 8,
      .dma_buf_len = BUFFER_LEN,
      .use_apll = false};
  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  const i2s_pin_config_t pin_config = {.bck_io_num = I2S_SCK,
                                       .ws_io_num = I2S_WS,
                                       .data_out_num = -1,
                                       .data_in_num = I2S_SD};
  i2s_set_pin(I2S_PORT, &pin_config);
  i2s_start(I2S_PORT);

  memset(preBuffer, 0, sizeof(preBuffer));
  xTaskCreatePinnedToCore(MicTask, "MicTask", 10000, NULL, 1, &Task1, 0);

  lcd.setCursor(0, 0);
  lcd.print("System Ready");
}

void MicTask(void *parameter) {
  size_t bytes_read;
  int32_t raw_buffer[BUFFER_LEN];
  for (;;) {
    i2s_read(I2S_PORT, &raw_buffer, BUFFER_LEN * 4, &bytes_read, portMAX_DELAY);
    if (bytes_read > 0) {
      long sum = 0;
      int16_t processed_chunk[BUFFER_LEN];
      for (int i = 0; i < bytes_read / 4; i++) {
        int16_t val = raw_buffer[i] >> 12;
        processed_chunk[i] = val;
        sum += abs(val);
        if (!isRecording) {
          preBuffer[preBufferHead] = val;
          preBufferHead++;
          if (preBufferHead >= PRE_BUF_SIZE)
            preBufferHead = 0;
        }
      }
      currentVolume = sum / (bytes_read / 4);
      if (isRecording)
        Serial.write((const uint8_t *)processed_chunk, (bytes_read / 4) * 2);
    }
  }
}

void updateVisualizer() {
  int bars = map(currentVolume, 500, 10000, 0, 16);
  if (bars > 16)
    bars = 16;

  lcd.setCursor(0, 1);
  for (int i = 0; i < 16; i++) {
    if (i < bars) {
      if (bars < 5)
        lcd.write(0);
      else if (bars < 10)
        lcd.write(2);
      else
        lcd.write(4);
    } else {
      lcd.print(" ");
    }
  }
}

void loop() {
  static unsigned long lastAudioTime = 0;
  static unsigned long lastVisTime = 0;
  static unsigned long lastPotRead = 0;
  static bool systemBusy = false;

  if (millis() - lastPotRead > 500) {
    int potValue = analogRead(POT_PIN);
    soundThreshold =
        map(potValue, 0, 4095, 1000, 8000);
    lastPotRead = millis();
  }

  if (Serial.available() > 0) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    if (msg.startsWith("THRESHOLD:")) {
      int newThreshold = msg.substring(10).toInt();
      if (newThreshold >= 1000 && newThreshold <= 8000) {
        soundThreshold = newThreshold;
        lcd.clear();
        lcd.print("Threshold:");
        lcd.setCursor(0, 1);
        lcd.print(soundThreshold);
        delay(1000);
        lcd.clear();
        lcd.print("System Ready");
      }
    } else if (msg == "SEARCHING") {
      systemBusy = true;
      lcd.clear();
      lcd.print("Searching...");
    } else if (msg == "FOUND") {
      systemBusy = true;
      lcd.clear();
      lcd.print("File Found!");
      digitalWrite(BUZZER_PIN, LOW);
      delay(30);
      digitalWrite(BUZZER_PIN, HIGH);
      delay(100);
      digitalWrite(BUZZER_PIN, LOW);
      delay(30);
      digitalWrite(BUZZER_PIN, HIGH);
      delay(3000);
      lcd.clear();
      lcd.print("System Ready");
      systemBusy = false;
    } else if (msg == "NOTFOUND") {
      systemBusy = true;
      lcd.clear();
      lcd.print("Not Found");
      delay(2000);
      lcd.clear();
      lcd.print("System Ready");
      systemBusy = false;
    }
  }

  if (!systemBusy && !isRecording) {
    if (millis() - lastVisTime > 100) {
      updateVisualizer();
      lastVisTime = millis();

      static int displayCycle = 0;
      if (displayCycle++ % 30 == 0) {
        lcd.setCursor(0, 0);
        lcd.print("Sens:");
        lcd.print(soundThreshold);
        lcd.print("    ");
      }
    }
  }

  if (!isRecording && currentVolume > soundThreshold) {
    isRecording = true;
    Serial.print("START_REC\n");
    lastAudioTime = millis();
    lcd.clear();
    lcd.print("Listening...");

    int len1 = PRE_BUF_SIZE - preBufferHead;
    if (len1 > 0)
      Serial.write((const uint8_t *)&preBuffer[preBufferHead], len1 * 2);
    if (preBufferHead > 0)
      Serial.write((const uint8_t *)&preBuffer[0], preBufferHead * 2);

    while (isRecording) {
      if (currentVolume > soundThreshold)
        lastAudioTime = millis();

      if (millis() - lastVisTime > 100) {
        updateVisualizer();
        lastVisTime = millis();
      }

      if (millis() - lastAudioTime > SILENCE_DURATION) {
        isRecording = false;
        Serial.print("STOP_REC");
        lcd.clear();
        lcd.print("Processing...");
      }
      delay(10);
    }
  }
}
