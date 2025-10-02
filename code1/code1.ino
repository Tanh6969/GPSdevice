
#include <TinyGPS++.h>
#include <HardwareSerial.h>
#include <SoftwareSerial.h>

// --- Config ---
#define A7682_RX 20
#define A7682_TX 21
#define GPS_RX 4
#define GPS_TX 5

const char adminNumber[] = "+84395667363"; // số điện thoại của bạn
const char serverIP[]    = "175.41.148.246"; // IP trực tiếp của server Flask
const int  serverPort    = 80; // HTTP port

// --- Objects ---
TinyGPSPlus gps;
HardwareSerial sim(1);                // UART1 cho A7682S
SoftwareSerial gpsSerial(GPS_RX,GPS_TX); // soft cho GPS

// --- State ---
bool mode1_enabled = false;
bool mode2_enabled = false;
double centerLat = 0.0, centerLon = 0.0;
double currentLat = 0.0, currentLon = 0.0;

// --- Helpers ---
void simSend(String cmd, int wait = 1000) {
  sim.println(cmd);
  delay(wait);
  while (sim.available()) {
    String r = sim.readString();
    Serial.println("SIM >>> " + r);
  }
}

void sendSMS(const char *number, String msg) {
  Serial.println("Sending SMS: " + msg);
  simSend("AT+CMGF=1", 500);
  sim.print("AT+CMGS=\"");
  sim.print(number);
  sim.println("\"");
  delay(500);
  sim.print(msg);
  sim.write(26); // Ctrl+Z
  delay(3000);
}

void makeMissedCall(const char *number) {
  Serial.println("Calling (missed call) to " + String(number));
  sim.print("ATD");
  sim.print(number);
  sim.println(";");
  delay(5000);
  simSend("ATH");
}

double distanceMeters(double lat1, double lon1, double lat2, double lon2) {
  const double R = 6371000;
  double dLat = radians(lat2 - lat1);
  double dLon = radians(lon2 - lon1);
  double a = sin(dLat/2)*sin(dLat/2) + cos(radians(lat1))*cos(radians(lat2))*sin(dLon/2)*sin(dLon/2);
  double c = 2 * atan2(sqrt(a), sqrt(1-a));
  return R * c;
}

// --- SMS Handler ---
void handleSMS(String smsText) {
  smsText.toUpperCase();
  Serial.println("Received SMS: " + smsText);

  if (smsText.indexOf("ONMODE1") >= 0) {
    if (gps.location.isValid()) {
      centerLat = gps.location.lat();
      centerLon = gps.location.lng();
      mode1_enabled = true;
      sendSMS(adminNumber, "MODE1 ON, Center set!");
    } else {
      sendSMS(adminNumber, "MODE1 ON, but GPS not fixed!");
    }
  }
  else if (smsText.indexOf("OFFMODE1") >= 0) {
    mode1_enabled = false;
    sendSMS(adminNumber, "MODE1 OFF");
  }
  else if (smsText.indexOf("ONMODE2") >= 0) {
    mode2_enabled = true;
    sendSMS(adminNumber, "MODE2 ON");
  }
  else if (smsText.indexOf("OFFMODE2") >= 0) {
    mode2_enabled = false;
    sendSMS(adminNumber, "MODE2 OFF");
  }
  else if (smsText.indexOf("CHECK") >= 0) {
    String msg = "POS: " + String(currentLat, 6) + "," + String(currentLon, 6) + "\n";
    msg += "MODE1: "; msg += (mode1_enabled ? "ON" : "OFF"); msg += "\n";
    msg += "MODE2: "; msg += (mode2_enabled ? "ON" : "OFF");
    sendSMS(adminNumber, msg);
  }
}

// --- SMS đọc ---
void checkIncomingSMS() {
  if (sim.available()) {
    String sms = sim.readString();
    if (sms.indexOf("+CMT:") >= 0) {
      int idx = sms.indexOf("\n", sms.indexOf("+CMT:"));
      if (idx > 0) {
        String content = sms.substring(idx);
        content.trim();
        handleSMS(content);
      }
    }
  }
}

// --- Mode1 kiểm tra ---
void checkMode1() {
  if (mode1_enabled && gps.location.isValid()) {
    currentLat = gps.location.lat();
    currentLon = gps.location.lng();
    double dist = distanceMeters(currentLat, currentLon, centerLat, centerLon);
    Serial.print("Mode1 distance: "); Serial.println(dist);
    if (dist > 7.0) {
      makeMissedCall(adminNumber);
      delay(60000);
    }
  }
}

// --- Gửi GPS qua CIPSTART/CIPSEND bằng IP ---
void sendGPS_HTTP(double lat, double lon, bool track) {
  String path = "/update?lat=" + String(lat, 6) + "&lon=" + String(lon, 6) + "&track=" + (track ? "1" : "0");
  String httpReq = "GET " + path + " HTTP/1.1\r\nHost: " + String(serverIP) + "\r\nConnection: close\r\n\r\n";

  Serial.println("HTTP REQ via CIPSTART:\n" + httpReq);

  // 1. Mở TCP
  simSend("AT+CIPSTART=\"TCP\",\"" + String(serverIP) + "\"," + String(serverPort), 5000);

  // 2. Gửi HTTP request
  simSend("AT+CIPSEND", 2000);
  sim.print(httpReq);
  sim.write(26); // Ctrl+Z
  delay(3000);

  // 3. Đọc phản hồi server
  while (sim.available()) {
    String r = sim.readString();
    Serial.println("SIM >>> " + r);
  }

  // 4. Đóng TCP
  simSend("AT+CIPCLOSE", 1000);
}

// --- GPS cập nhật ---
void updateGPS() {
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    Serial.print(c);
    gps.encode(c);
  }

  if (gps.location.isUpdated()) {
    currentLat = gps.location.lat();
    currentLon = gps.location.lng();
    Serial.print("GPS FIX: "); 
    Serial.print(currentLat, 6); 
    Serial.print(", "); 
    Serial.println(currentLon, 6);
    Serial.print("SAT: "); Serial.println(gps.satellites.value());
    Serial.print("ALT: "); Serial.println(gps.altitude.meters());
    Serial.println("----------------------");
  }
}

void checkNetworkStatus() {
  Serial.println("=== Network Status Check ===");
  simSend("AT");
  simSend("AT+CSQ", 2000);
  simSend("AT+CREG?", 2000);
  simSend("AT+COPS?", 2000);
  simSend("AT+CGATT?", 2000);
  simSend("AT+CGACT?", 2000);
  simSend("AT+CGDCONT?", 2000);
  Serial.println("============================");
}

void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600);
  sim.begin(115200, SERIAL_8N1, A7682_RX, A7682_TX);

  delay(3000); // đợi SIM khởi động

  // Kiểm tra SIM
  simSend("AT", 1000);
  simSend("AT+CMGF=1", 1000);
  simSend("AT+CNMI=1,2,0,0,0", 1000);

  // GPRS attach + APN Viettel
  simSend("AT+CGATT=1", 2000);  
  simSend("AT+CGDCONT=1,\"IP\",\"v-internet\"", 2000);  
  simSend("AT+CGACT=1,1", 5000);   

  // Kiểm tra trạng thái mạng
  checkNetworkStatus();

  // Ban đầu tất cả mode OFF
  mode1_enabled = false;
  mode2_enabled = false;

  Serial.println("System ready. Modes set to OFF.");
}

void loop() {
  updateGPS();          // luôn cập nhật GPS
  checkIncomingSMS();   // kiểm tra SMS
  checkMode1();         // kiểm tra Mode1

  static unsigned long lastSend = 0;
  if (gps.location.isValid() && millis() - lastSend > 15000) {
    sendGPS_HTTP(currentLat, currentLon, mode2_enabled); // track = true nếu Mode2 ON
    lastSend = millis();
  }

  delay(500); // vòng lặp nhẹ, không block GPS/SMS
}