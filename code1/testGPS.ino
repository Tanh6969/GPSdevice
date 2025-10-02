#include <TinyGPS++.h>
#include <HardwareSerial.h>

TinyGPSPlus gps;
HardwareSerial gpsSerial(1);  // UART1

void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600, SERIAL_8N1, 4, 5); // RX=4, TX=5
  Serial.println("GPS test starting...");
}

void loop() {
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    Serial.print(c);   // In thẳng chuỗi NMEA để xem GPS có gửi gì không
    gps.encode(c);
  }

  if (gps.location.isUpdated()) {
    Serial.print("LAT="); Serial.println(gps.location.lat(), 6);
    Serial.print("LON="); Serial.println(gps.location.lng(), 6);
    Serial.print("ALT="); Serial.println(gps.altitude.meters());
    Serial.print("SAT="); Serial.println(gps.satellites.value());
    Serial.println("------------------");
  }
}
