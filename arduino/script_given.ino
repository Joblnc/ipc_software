#include <SPI.h>

#include <WiFiNINA.h>
#include <WiFiUdp.h>
// #include <WiFiClient.h> USELESS because already included in WifiNina
#include "hardware/pwm.h"
// #include "clocks.h" Not used for the moment
//#include "freqs.h"
char ssid[] = "TP-Link_BB34";
char pass[] = "75288426"; 
int status = WL_IDLE_STATUS;
const IPAddress REMOTE_IP(192,168,0,255);
const IPAddress REMOTE_IP_TCP(192,168,0,102);
const uint16_t LOCAL_PORT  = 23456;
const uint8_t PIN_ADC = A0;
const uint16_t REMOTE_PORT = 12345;
const uint16_t LOCAL_TCP_PORT=20000;
const uint16_t REMOTE_TCP_PORT=20000;
//PWM LUT (czestotliwosci i ich parametry)



WiFiUDP udp;

// Definition of a struct and an array

typedef struct {  uint16_t top; uint8_t div_int; uint8_t div_frac; } pwm_config_t;
pwm_config_t pwm_lut[700] = {};

#define PWM_LUT_SIZE 700
static uint16_t adc_buffer[PWM_LUT_SIZE];


//
void waitforwifi(){
    PinStatus led=HIGH;
    status=WiFi.status();
    bool blink=true;
    while (status != WL_CONNECTED){
        if(blink) {
            blink=!blink;
            led=LOW;
        }
        else {
            blink=!blink;
            led=HIGH;
        }
        digitalWrite(LEDR, led);
        status = WiFi.begin(ssid, pass);
        delay(1000);
    }
}
//
void setup() {
    // put your setup code here, to run once:
    pinMode(LEDR, OUTPUT);
    pinMode(LEDG, OUTPUT);
    pinMode(LEDB, OUTPUT);
    pinMode(12,OUTPUT);
    digitalWrite(LEDG, LOW);
    Serial.begin(9600);
    String fv = WiFi.firmwareVersion();


    if (fv < WIFI_FIRMWARE_LATEST_VERSION) {


        Serial.println("Please upgrade the firmware");


    }
    PinStatus led=HIGH;
    bool blink=true;
    digitalWrite(LEDR, HIGH);
    while (status != WL_CONNECTED) {


        Serial.print("Attempting to connect to WPA SSID: ");
        if(blink) {
            blink=!blink;
            led=LOW;
        }
        else {
            blink=!blink;
            led=HIGH;
        }
        digitalWrite(LEDR, led);


        Serial.println(ssid);


        // Connect to WPA/WPA2 network:


        status = WiFi.begin(ssid, pass);


        // wait 10 seconds for connection:


        delay(1000);



    }
    digitalWrite(LEDR, LOW);
    digitalWrite(LEDG, HIGH);

    Serial.print("You're connected to the network");
    gpio_set_function(18, GPIO_FUNC_PWM);

    udp.begin(REMOTE_PORT);
    analogReadResolution(12);

}
void set_pwm(uint slice,uint16_t top, uint8_t div_int,uint8_t div_frac){
    pwm_set_counter(slice, 0);
    pwm_set_clkdiv_int_frac(slice,div_int,div_frac);
    pwm_set_wrap(slice,top);
    pwm_set_chan_level(slice,PWM_CHAN_A,(top+1)/2);
}
void loop_pwm(pwm_config_t array[300],uint16_t amount,uint8_t slice,uint16_t delay){
    pwm_set_enabled(slice,true);
    digitalWrite(12, HIGH);
    for (size_t i=0; i<amount;i++){
        auto &cfg=array[i];
        set_pwm(slice,cfg.top,cfg.div_int,cfg.div_frac);
        delayMicroseconds(delay);
        adc_buffer[i] = analogRead(PIN_ADC);
    }
    digitalWrite(12, LOW);

}
WiFiClient client;
uint slice=pwm_gpio_to_slice_num(18);
enum state{
    COMMAND_WAIT,FREQUENCY_ADD
};
state current_state=COMMAND_WAIT;
bool sweep= false;
uint16_t delay_time= 1000;
uint16_t freq_amount=300;
void loop() {
    //block that checks WIFI status and attempts to reconnect to it
    PinStatus led=HIGH;
    bool blink=true;
    while (status != WL_CONNECTED) {


        Serial.print("Attempting to connect to WPA SSID: ");
        if(blink) {
            blink=!blink;
            led=LOW;
        }
        else {
            blink=!blink;
            led=HIGH;
        }
        digitalWrite(LEDR, led);


        Serial.println(ssid);


        // Connect to WPA/WPA2 network:


        status = WiFi.begin(ssid, pass);


        // wait 10 seconds for connection:


        delay(1000);



    }
    //
    if (client.connected()){
        digitalWrite(LEDR, LOW);
        digitalWrite(LEDG, HIGH);
        digitalWrite(LEDB, LOW);
        if(client.available()){
            if(current_state==COMMAND_WAIT){
                uint8_t buffer=client.read();
                switch (buffer){
                    case 0:{ //stop
                               sweep=false;

                           }
                           break;
                    case 1:{ //start
                               sweep=true;

                           }
                           break;
                    case 2:{ //set delay
                               uint8_t delay_buf[2];
                               int read=0;
                               while(read<2){
                                   if(client.available()){
                                       delay_buf[read]=client.read();
                                       read++;
                                   }
                               }
                               delay_time=*reinterpret_cast<uint16_t*>(delay_buf);
                               //client.read(reinterpret_cast<uint8_t*>(&delay_time), 2);


                           }
                           break;
                    case 3:{
                               current_state=FREQUENCY_ADD;
                               return;
                           }
                           break;
                }
            }
            else if(current_state==FREQUENCY_ADD){ //nasłuchujemy na czestotliwosci
                if(client.available()>=2){
                    client.read(reinterpret_cast<uint8_t*>(&freq_amount),2);
                }
                else return;
                uint16_t i=0;
                while (i<freq_amount){
                    digitalWrite(LEDR, LOW);
                    digitalWrite(LEDG, LOW);
                    digitalWrite(LEDB, LOW);
                    if(client.available()>=4){
                        uint8_t buf[4];
                        client.read(buf,4);
                        pwm_config_t* new_data=reinterpret_cast<pwm_config_t*>(buf);
                        pwm_lut[i]=*new_data;
                        i++;
                        digitalWrite(LEDR, HIGH);
                        digitalWrite(LEDG, HIGH);
                        digitalWrite(LEDB, HIGH);
                    }
                }
                current_state=COMMAND_WAIT;
                return;
            }
        }
    }
    else {
        waitforwifi();
        digitalWrite(LEDR, HIGH);
        digitalWrite(LEDG, HIGH);
        digitalWrite(LEDB, LOW);
        current_state=COMMAND_WAIT;
        client.connect(REMOTE_IP_TCP,REMOTE_TCP_PORT);
    }
    // put your main code here, to run repeatedly:

    if(!sweep){
        return;
    }
    loop_pwm(pwm_lut, freq_amount, slice, delay_time);
    udp.beginPacket(REMOTE_IP, REMOTE_PORT);
    udp.write((uint8_t*)adc_buffer,
            freq_amount * sizeof(adc_buffer[0]));
    udp.endPacket();
}
