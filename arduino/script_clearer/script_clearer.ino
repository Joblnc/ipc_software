/*
 * INTERNET OF PLANTS PROJECT - MODE DIFFÉRENTIEL (LOUPE)
 * HardWare: Arduino Nano RP2040 Connect
 */

#include <SPI.h>
#include "hardware/pwm.h"
#include "clocks.h" 

// === CONFIGURATION ===
const uint8_t PIN_ADC_INPUT = A0;   
const uint8_t PIN_PWM_OUTPUT = 6;  // Remplacé par D6 (GPIO 6 natif sur RP2040)
const uint8_t LED_Witness = 12;     

typedef struct {
  uint16_t top;       
  uint8_t div_int;    
  uint8_t div_frac;   
} pwm_config_t;

#define MAX_FREQUENCIES 700
pwm_config_t frequency_list[MAX_FREQUENCIES] = {};
static uint16_t measurement_buffer[MAX_FREQUENCIES];
static uint16_t baseline_buffer[MAX_FREQUENCIES]; // NOUVEAU : Mémoire de référence

uint16_t delay_between_freqs_us = 1000; 
uint16_t frequency_count = 0;           
uint pwm_slice;                         

// === UTILS FUNCTIONS ===

void configurePWM(uint slice, uint16_t top, uint8_t div_int, uint8_t div_frac) {
  pwm_set_counter(slice, 0);
  pwm_set_clkdiv_int_frac(slice, div_int, div_frac);
  pwm_set_wrap(slice, top);
  pwm_set_chan_level(slice, PWM_CHAN_A, (top + 1) / 2); 
}

void performFrequencySweep(uint slice, uint16_t* buffer_to_fill) {
  pwm_set_enabled(slice, true);
  digitalWrite(LED_Witness, HIGH);

  for (size_t i = 0; i < frequency_count; i++) {
    auto &cfg = frequency_list[i];
    configurePWM(slice, cfg.top, cfg.div_int, cfg.div_frac);
    delayMicroseconds(delay_between_freqs_us);
    
    // Remplit le tableau qu'on lui a passé en paramètre
    buffer_to_fill[i] = analogRead(PIN_ADC_INPUT);
  }

  digitalWrite(LED_Witness, LOW);
  pwm_set_enabled(slice, false); 
}

// === SETUP ===

void setup() {
  pinMode(LED_Witness, OUTPUT);
  Serial.begin(115200); 
  
  // Petite pause pour laisser le temps d'ouvrir le Traceur Série
  delay(3000); 

  gpio_set_function(PIN_PWM_OUTPUT, GPIO_FUNC_PWM);
  analogReadResolution(12); 
  pwm_slice = pwm_gpio_to_slice_num(PIN_PWM_OUTPUT);

  // Génération des 24 fréquences
  for (uint32_t freq = 20000; freq <= 250000; freq += 10000) {
    frequency_list[frequency_count].top = (125000000 / freq) - 1;
    frequency_list[frequency_count].div_int = 1;
    frequency_list[frequency_count].div_frac = 0;
    frequency_count++;
  }
  
  // --- NOUVEAU : CALIBRATION DE LA LIGNE DE BASE ---
  // On fait un premier balayage "à vide" et on le sauvegarde dans le baseline_buffer
  performFrequencySweep(pwm_slice, baseline_buffer);
}

// === LOOP ===

void loop() {
  // 1. Fait une nouvelle mesure et la stocke dans le measurement_buffer
  performFrequencySweep(pwm_slice, measurement_buffer);
  
  // 2. Affiche la DIFFÉRENCE
  for (size_t i = 0; i < frequency_count; i++) {
    // Calcul de la différence (on utilise 'int' car le résultat peut être négatif)
    int difference = (int)measurement_buffer[i] - (int)baseline_buffer[i];

    // On fige l'axe Y très serré autour de 0 pour faire l'effet "loupe"
    Serial.print("Min:-150, ");
    Serial.print("Max:150, ");
    Serial.print("Zero_Ref:0, "); // Dessine une ligne plate à 0 pour repère visuel
    
    Serial.print("Variation:");
    Serial.println(difference);
    
    delay(20); 
  }

  // Pause de 2 secondes
  delay(2000); 
}