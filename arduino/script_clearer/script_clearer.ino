/*
 * INTERNET OF PLANTS PROJECT
 * HardWare: Arduino Nano RP2040 Connect
 * Description: This script sends different sequences to the plant (PWM) and 
 *  measures the plant answer with ADC. Data is then sent to the TCP server with UDP
 *  The system is driven by a TCP Server, in Python
 */

#include <SPI.h>
#include <WiFiNINA.h>
#include <WiFiUdp.h>
#include <WiFiClient.h>

// libraries specific to RP2040 : necessaries to generate pwm frequencies
#include "hardware/pwm.h"
#include "clocks.h" 

// === CONFIGURATION ===

// WiFi identifiers
const char ssid[] = "VOTRE_WIFI_SSID";     // to change
const char pass[] = "VOTRE_WIFI_PASSWORD"; // to change

// IP Adresses
// data collecter computer ip (maybe have to change it)
const IPAddress PC_DATA_IP(192, 168, 1, 50); 
const uint16_t PC_DATA_PORT_UDP = 12345;

*// server ip (maybe have to change it)
const IPAddress PC_CONTROL_IP(192, 168, 1, 50);
const uint16_t PC_CONTROL_PORT_TCP = 20000;

// Hardware Pins
const uint8_t PIN_ADC_INPUT = A0;   // Reads the plant answer
const uint8_t PIN_PWM_OUTPUT = 18;  // Sends the signal (18 = A2 on the card)
const uint8_t LED_Witness = 12;      // LED that turns on during measuring

// === DATA STRUCTURES ===

// Structure that defines a specific frequency for the pwm (Pulse Width Modulation)
// Goal of the structure : dividing the frequence of RP2040 (125 MHz) to send somthing 
// reasonable to the plant
typedef struct {
  uint16_t top;       // max value of the counter, defines the period
  uint8_t div_int;    // divides the frequency by an integer
  uint8_t div_frac;   // adjusts the previous result by dividing with a float
} pwm_config_t;

// Arrays to stock sent frequencies and answers gotten
#define MAX_FREQUENCIES 700
pwm_config_t frequency_list[MAX_FREQUENCIES] = {}; // List of the frequencies to send (the server imposes it)
static uint16_t measurement_buffer[MAX_FREQUENCIES]; // List of the answers of the plant for each frequency sent

// Global Variables
WiFiUDP udp;
WiFiClient tcpClient;
int wifiStatus = WL_IDLE_STATUS;

$// Measurement parameters (editable by the TCP server) 
uint16_t delay_between_freqs_us = 1000; // time to wait between each signal that we send (in micro seconds)
uint16_t frequency_count = 300;         // number of frequency analysed
bool isScanning = false;                // System state (on / off)

// States of the arduino
enum State {
  WAITING_FOR_COMMAND,
  RECEIVING_FREQUENCY_LIST
};
State currentState = WAITING_FOR_COMMAND;

// === UTILS FUNCTIONS ===

// function to connect to wifi with blinking led
void connectToWiFi() {
  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  
  // if red is on, then not connected
  digitalWrite(LEDR, HIGH); 
  digitalWrite(LEDG, LOW);

  Serial.print("connexion attempt to SSID: ");
  Serial.println(ssid);

  while (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(ssid, pass);
    // blinking while waiting for connexion
    digitalWrite(LEDR, LOW); delay(250);
    digitalWrite(LEDR, HIGH); delay(250);
    Serial.print(".");
  }

  // green on => connected
  Serial.println("\nConnected to WiFi !");
  digitalWrite(LEDR, LOW);
  digitalWrite(LEDG, HIGH);
}

// Configuration of the pwm on the RP2040
void configurePWM(uint slice, uint16_t top, uint8_t div_int, uint8_t div_frac) {
  pwm_set_counter(slice, 0);
  pwm_set_clkdiv_int_frac(slice, div_int, div_frac);
  pwm_set_wrap(slice, top);
  pwm_set_chan_level(slice, PWM_CHAN_A, (top + 1) / 2);
}

// principal function : sends the different frequences to the plant and read the answers
void performFrequencySweep(uint slice) {
  pwm_set_enabled(slice, true); // activates the pwm generator
  digitalWrite(LED_Witness, HIGH); // turns on the witness led

  // iterates over the frequency list
  for (size_t i = 0; i < frequency_count; i++) {
    // configures the current frequency
    auto &cfg = frequency_list[i];
    configurePWM(slice, cfg.top, cfg.div_int, cfg.div_frac);
    
    // waits for the signal to stabilize
    delayMicroseconds(delay_between_freqs_us);
    
    // reads the plant answer
    measurement_buffer[i] = analogRead(PIN_ADC_INPUT);
  }

  digitalWrite(LED_Witness, LOW); // Turns off the led
  // Note: to keep continuity, we don't turn off the pwm, but we could add 
  // pwm_set_enabled(slice, false);
}

// === SETUP AND LOOP ===

void setup() {
  // Pins Initialization
  pinMode(LED_Witness, OUTPUT);
  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  pinMode(LEDB, OUTPUT);
  
  Serial.begin(9600);
  
  // Cheks the FirmWare WiFi
  if (WiFi.firmwareVersion() < WIFI_FIRMWARE_LATEST_VERSION) {
    Serial.println("ATTENTION: Please update the FirmWare wifi");
  }

  // WiFi Connection
  connectToWiFi();

  // PWM pin configuration (18, or A2)
  gpio_set_function(PIN_PWM_OUTPUT, GPIO_FUNC_PWM);
  
  // ADC configuration : 12 bits resolution => values from 0 to 4095
  analogReadResolution(12);

  // UDP Start
  udp.begin(PC_DATA_PORT_UDP);
}

// gets the controlling slice of the 18 (aka A2) port
uint pwm_slice = pwm_gpio_to_slice_num(PIN_PWM_OUTPUT);

void loop() {
  
  // Reconnects automatically to wifi if it lost connection
  if (WiFi.status() != WL_CONNECTED) {
    connectToWiFi();
    tcpClient.stop(); 
  }

  // TCP connection management : while we are not connected, we try to connect to the 
  // TCP server again
  if (!tcpClient.connected()) {
    Serial.println("Connection attempt ...");
    tcpClient.connect(PC_CONTROL_IP, PC_CONTROL_PORT_TCP);
    delay(1000); // 1s delay to not spam
    return;
  }

  // Reads TCP commands
  if (tcpClient.available()) {
    
    if (currentState == WAITING_FOR_COMMAND) {
      uint8_t command = tcpClient.read();
      
      switch (command) {
        case 0: // STOP
          isScanning = false;
          Serial.println("CMD: Stop Scanning");
          break;
          
        case 1: // START
          isScanning = true;
          Serial.println("CMD: Start Scanning");
          break;
          
        case 2: // SET DELAY
          // Reads 2 bytes to form a uint16_t
          tcpClient.readBytes((char*)&delay_between_freqs_us, 2);
          Serial.print("CMD: Delay set to "); Serial.println(delay_between_freqs_us);
          break;
          
        case 3: // LOAD FREQUENCIES
          currentState = RECEIVING_FREQUENCY_LIST; // Switch state to receive big list
          Serial.println("CMD: Loading Frequencies...");
          break;
      }
    }
    
    else if (currentState == RECEIVING_FREQUENCY_LIST) {
      // Reads the number of frequencies we'll get, on 2 bytes
      if (tcpClient.available() >= 2) {
         tcpClient.readBytes((char*)&frequency_count, 2);
         if(frequency_count > MAX_FREQUENCIES) frequency_count = MAX_FREQUENCIES; // Max value if it is asked for more
      }
      
      // fills the array with what is asked by the server
      // note : not professional, it is waiting to receive all data : maybe we should add a timeout
      uint16_t loaded = 0;
      while (loaded < frequency_count) {
        if (tcpClient.available() >= sizeof(pwm_config_t)) {
          tcpClient.readBytes((char*)&frequency_list[loaded], sizeof(pwm_config_t));
          loaded++;
        }
      }
      Serial.println("Frequencies Loaded.");
      currentState = WAITING_FOR_COMMAND; // Indicates that frequencies are loaded
    }
  }

  // if it is scanning, sweeps
  if (isScanning) {
    performFrequencySweep(pwm_slice);

    // send the results (i.e. the answers of the plant to each frequency)
    udp.beginPacket(PC_DATA_IP, PC_DATA_PORT_UDP);
    udp.write((uint8_t*)measurement_buffer, frequency_count * sizeof(uint16_t));
    udp.endPacket();
  }
}