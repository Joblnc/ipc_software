/*
 * INTERNET OF PLANTS PROJECT - MODE DIFFÉRENTIEL (LOUPE)
 * HardWare: Arduino Nano RP2040 Connect
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
const char ssid[] = "Wifi_Atelier";     // to change
const char pass[] = "MakerSpace69"; // to change

// IP Adresses
// data collecter computer ip (maybe have to change it)
const IPAddress PC_DATA_IP(192, 168, 1, 102); 
const uint16_t PC_DATA_PORT_UDP = 12345;

// server ip (maybe have to change it)
const IPAddress PC_CONTROL_IP(192, 168, 1, 102);
const uint16_t PC_CONTROL_PORT_TCP = 20000;

// Hardware Pins
const uint8_t PIN_ADC_INPUT = A0;   // Reads the plant answer
const uint8_t PIN_PWM_OUTPUT = 6;   // Sends the signal
const uint8_t LED_Witness = 12;     // LED that turns on during measuring

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
pwm_config_t frequency_list[MAX_FREQUENCIES] = {};
static uint16_t measurement_buffer[MAX_FREQUENCIES];
static uint16_t measurement_buffer_prev[MAX_FREQUENCIES]; // Memory of previous sweep
static uint16_t baseline_buffer[MAX_FREQUENCIES]; // Reference memory

// Global Variables
WiFiUDP udp;
WiFiClient tcpClient;
int wifiStatus = WL_IDLE_STATUS;

// Measurement parameters (editable by the TCP server) 
uint16_t delay_between_freqs_us = 1000;  // time to wait between each signal that we send (in micro seconds)
uint16_t frequency_count = 0;            // number of frequency analysed
bool isScanning = false;                 // System state (on / off)
uint pwm_slice;                         

// States of the arduino
enum State {
  WAITING_FOR_COMMAND,
  RECEIVING_FREQUENCY_LIST
};
State currentState = WAITING_FOR_COMMAND;

// Debug variable, for visual result on the serial plotter
bool debug = 0;

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

  uint chan = pwm_gpio_to_channel(PIN_PWM_OUTPUT); 
  pwm_set_chan_level(slice, chan, (top + 1) / 2);
  //pwm_set_chan_level(slice, PWM_CHAN_A, (top + 1) / 2); 
}

// principal function : sends the different frequences to the plant and read the answers
void performFrequencySweep(uint slice, uint16_t* buffer_to_fill) {
  pwm_set_enabled(slice, true);     // activates the pwm generator
  digitalWrite(LED_Witness, HIGH);  // turns on the witness led

  // iterates over the frequency list
  for (size_t i = 0; i < frequency_count; i++) {
    // configures the current frequency
    auto &cfg = frequency_list[i];
    configurePWM(slice, cfg.top, cfg.div_int, cfg.div_frac);

    // waits for the signal to stabilize
    delayMicroseconds(delay_between_freqs_us);
    
    // fills the array with answers of the plant
    buffer_to_fill[i] = analogRead(PIN_ADC_INPUT);
  }

  digitalWrite(LED_Witness, LOW);  // Turns off the led
  pwm_set_enabled(slice, false); 
}

// === SETUP ===

void setup() {
  // Pins initialization
  pinMode(LED_Witness, OUTPUT);
  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  pinMode(LEDB, OUTPUT);

  Serial.begin(115200); 
  
  // Cheks the FirmWare WiFi
  if (WiFi.firmwareVersion() < WIFI_FIRMWARE_LATEST_VERSION) {
    Serial.println("ATTENTION: Please update the FirmWare wifi");
  }

  // WiFi Connection
  connectToWiFi();

  // small break to let time to open serial tracer
  delay(3000); 

  // PWM pin configuration (D6)
  gpio_set_function(PIN_PWM_OUTPUT, GPIO_FUNC_PWM);

  // ADC configuration : 12 bits resolution => values from 0 to 4095
  analogReadResolution(12); 

  // UDP Start
  udp.begin(PC_DATA_PORT_UDP);

  pwm_slice = pwm_gpio_to_slice_num(PIN_PWM_OUTPUT);

  if (debug == 1){
    // generates specific frequences
    for (uint32_t freq = 20000; freq <= 250000; freq += 10000) {
      frequency_list[frequency_count].top = (125000000 / freq) - 1;
      frequency_list[frequency_count].div_int = 1;
      frequency_list[frequency_count].div_frac = 0;
      frequency_count++;
    }
    
    // Reference line calibration : first sweep on nothing 
    performFrequencySweep(pwm_slice, baseline_buffer);
  }
}

// === LOOP ===

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
    
    else if (currentState == RECEIVING_FREQUENCY_LIST && debug == 0) {
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

  if (debug == 1 || isScanning){
    // stores prev measurements in the corresponding buffer
    for (int i = 0; i < MAX_FREQUENCIES; i++){
      measurement_buffer_prev[i] = measurement_buffer[i];
    }
    // stores new measures in measurment buffer
    performFrequencySweep(pwm_slice, measurement_buffer);
    
    // displays difference between measurements and references
    for (size_t i = 0; i < frequency_count; i++) {
      // difference calculation
      int difference = (int)measurement_buffer[i] - (int)baseline_buffer[i];
      int difference_prev = (int)measurement_buffer_prev[i] - (int)baseline_buffer[i];
      // set y axis around 0 to make a zoom effect
      Serial.print("Min:-150, ");
      Serial.print("Max:1000, ");
      Serial.print("Zero_Ref:0, "); // Draws a line on 0 as reference
      
      Serial.print("Current_Variation:");
      Serial.print(difference);
      Serial.print(",");

      Serial.print("Prev_Variation:");
      Serial.print(difference_prev);
      Serial.print(",");

      Serial.print("Sweep_separator:");
      Serial.println(-150);

      delay(20); 
    }

    // displays the sweep separator 
    Serial.print("Min:-150,");
    Serial.print("Max:1000,");
    Serial.print("Zero_Ref:0,"); 
    // On met les courbes à 0 (ou on pourrait garder la dernière valeur)
    // BOUM : Le séparateur saute tout en haut !
    Serial.print("Separateur:");
    Serial.println(1000);

    // send the results (i.e. the answers of the plant to each frequency)
    udp.beginPacket(PC_DATA_IP, PC_DATA_PORT_UDP);
    udp.write((uint8_t*)measurement_buffer, frequency_count * sizeof(uint16_t));
    udp.endPacket();
  }
  

  // 2 seconds break
  delay(2000); 
}