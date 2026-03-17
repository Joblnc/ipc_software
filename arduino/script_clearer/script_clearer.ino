/*
 * INTERNET OF PLANTS PROJECT - LOCAL TEST VERSION
 * HardWare: Arduino Nano RP2040 Connect
 * Description: Ce script envoie différentes fréquences à la plante (PWM) et 
 * mesure la réponse avec l'ADC. Les résultats sont affichés sur le Moniteur Série.
 */

#include <SPI.h>
// librairies spécifiques au RP2040 pour générer le PWM
#include "hardware/pwm.h"
#include "clocks.h" 

// === CONFIGURATION ===

// Hardware Pins
const uint8_t PIN_ADC_INPUT = A0;   // Lit la réponse de la plante
const uint8_t PIN_PWM_OUTPUT = 18;  // Envoie le signal (18 = A2 sur la carte)
const uint8_t LED_Witness = 12;     // LED témoin pendant la mesure

// === DATA STRUCTURES ===

typedef struct {
  uint16_t top;       // valeur max du compteur (définit la période)
  uint8_t div_int;    // diviseur entier
  uint8_t div_frac;   // diviseur fractionnaire
} pwm_config_t;

#define MAX_FREQUENCIES 700
pwm_config_t frequency_list[MAX_FREQUENCIES] = {};
static uint16_t measurement_buffer[MAX_FREQUENCIES];

// Paramètres de mesure
uint16_t delay_between_freqs_us = 1000; // Temps d'attente pour stabiliser le signal
uint16_t frequency_count = 0;           // Sera calculé dans le setup
uint pwm_slice;                         // Slice PWM du RP2040

// === UTILS FUNCTIONS ===

void configurePWM(uint slice, uint16_t top, uint8_t div_int, uint8_t div_frac) {
  pwm_set_counter(slice, 0);
  pwm_set_clkdiv_int_frac(slice, div_int, div_frac);
  pwm_set_wrap(slice, top);
  pwm_set_chan_level(slice, PWM_CHAN_A, (top + 1) / 2); // Duty cycle de 50%
}

void performFrequencySweep(uint slice) {
  pwm_set_enabled(slice, true);
  digitalWrite(LED_Witness, HIGH);

  for (size_t i = 0; i < frequency_count; i++) {
    auto &cfg = frequency_list[i];
    configurePWM(slice, cfg.top, cfg.div_int, cfg.div_frac);
    
    delayMicroseconds(delay_between_freqs_us);
    
    measurement_buffer[i] = analogRead(PIN_ADC_INPUT);
  }

  digitalWrite(LED_Witness, LOW);
  pwm_set_enabled(slice, false); // On coupe le signal entre les salves de mesures
}

// === SETUP AND LOOP ===

void setup() {
  pinMode(LED_Witness, OUTPUT);
  
  // Vitesse plus élevée pour ne pas ralentir l'affichage
  Serial.begin(115200); 
  
  // Attente que le moniteur série soit ouvert (pratique pour ne rien rater au démarrage)
  while (!Serial);
  Serial.println("=== Démarrage du test d'impédance local ===");

  gpio_set_function(PIN_PWM_OUTPUT, GPIO_FUNC_PWM);
  analogReadResolution(12); // Résolution 12 bits => 0 à 4095
  pwm_slice = pwm_gpio_to_slice_num(PIN_PWM_OUTPUT);

  // --- GÉNÉRATION DES FRÉQUENCES EN LOCAL ---
  // On génère des fréquences de 20 kHz à 250 kHz par pas de 10 kHz
  Serial.println("Génération de la liste des fréquences...");
  for (uint32_t freq = 20000; freq <= 250000; freq += 10000) {
    // Formule RP2040: top = (SystemClock / Frequence) - 1
    // Horloge système RP2040 = 125 MHz
    frequency_list[frequency_count].top = (125000000 / freq) - 1;
    frequency_list[frequency_count].div_int = 1;
    frequency_list[frequency_count].div_frac = 0;
    frequency_count++;
  }
  
  Serial.print(frequency_count);
  Serial.println(" fréquences prêtes à être testées.");
}

void loop() {
  // 1. Fait la mesure (balayage des 24 fréquences)
  performFrequencySweep(pwm_slice);
  
  // 2. Affiche les résultats au format Traceur Série
  for (size_t i = 0; i < frequency_count; i++) {
    // Fige l'axe Y pour avoir une vue stable
    Serial.print("Min:0, ");
    Serial.print("Max:4095, ");
    
    // Envoie la valeur lue
    Serial.print("Amplitude:");
    Serial.println(measurement_buffer[i]);
    
    // Petit délai pour que la courbe se dessine de manière fluide à l'écran
    delay(20); 
  }

  // Pause de 2 secondes avant de lancer le prochain balayage
  delay(2000); 
}