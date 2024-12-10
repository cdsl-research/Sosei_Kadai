import network
import usocket as socket
import uasyncio as asyncio
import json
import machine
import utime
import time
import select
import gc
import _thread
import os
from machine import I2C, Pin



# グローバル変数
sta_if = network.WLAN(network.STA_IF)
received_sequence_numbers = set()
total_packets = 750
packet_loss_list = []
duplicate_packets = 0
program_finished = False
timeout_thread_running = False
last_count = 0
received_count = 0
full_set = set(range(750))
new_access = 0
event_flag = 0
now_time = time.time() #現在時刻


# 定数
DMG_IP = '239.255.255.250'
DMG_PORT = 50006
SERVER_IP = ''
SERVER_PORT = 50005
UNICAST_PORT = 50010  # ユニキャスト用のポート


# プログラム開始時間
program_start_time = time.time()

def inet_aton(ip):
    parts = [int(part) for part in ip.split('.')]
    return bytes(parts)

    #CSV1つにした
def write_experiment_results_to_csv(filename, completion_time, duplicate_packets_count):
    """
    completion_time: プログラムの完了時間
    duplicate_packets_count: 重複パケットの数
    total_power_mw:総処理電力
    """

    # ファイルが存在するかどうかをチェック
    if file_exists(filename):
        mode = 'a'
    else:
        mode = 'w'

    with open(filename, mode) as csvfile:
        # 新しいファイルの場合、ヘッダーを書き込む
        if mode == 'w':
            csvfile.write("Completion Time (seconds), Duplicate Packets\n")
        # 結果を1行にまとめて書き込む
        csvfile.write(f"{completion_time}, {duplicate_packets_count}\n")

    print(f"Experiment results (Completion Time: {completion_time} seconds, Duplicate Packets: {duplicate_packets_count}) have been written to {filename}")

    


def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False

def connect_wifi(ssid, password):
    global sta_if
    if not sta_if.isconnected():
        print('Connecting to WiFi...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        timeout = 30
        start_time = utime.time()
        while not sta_if.isconnected():
            if utime.time() - start_time > timeout:
                print('Failed to connect to WiFi: Timeout')
                return False
            time.sleep(1)
    print('Network configuration:', sta_if.ifconfig())
    return True

def setup_multicast_socket():
    mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mcast_sock.bind(('0.0.0.0', DMG_PORT))
#    mreq = inet_aton(DMG_IP) + inet_aton('0.0.0.0')
    mreq = b''.join([inet_aton(DMG_IP), inet_aton('0.0.0.0')])

    mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return mcast_sock


# ユニキャストソケットの設定
def setup_unicast_socket():
    global unicast_sock
    ip_address = sta_if.ifconfig()[0]
    unicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # SO_REUSEADDRオプションを設定
    unicast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        unicast_sock.bind(('0.0.0.0', UNICAST_PORT))
    except OSError as e:
        print(f"Error binding unicast socket: {e}")
        # ポートが使用中の場合、別のポートを試す
        for port in range(UNICAST_PORT, UNICAST_PORT + 10):
            try:
                unicast_sock.bind(('0.0.0.0', port))
                print(f"Successfully bound to port {port}")
                return unicast_sock
            except:
                continue
        raise RuntimeError("Could not bind to any port")
    
    unicast_sock.setblocking(False)
    return unicast_sock

async def receive_multicast(mcast_sock, timeout_sec):
    global received_sequence_numbers, packet_loss_list, duplicate_packets,program_start_time,new_access,event_flag,now_time
    
    start_time = time.time()
    last_seq = -1
    last_packet_time = time.time()
    resend_notification_time = None
    expected_resend_sequence = None
    resend_list = []
    missing_packets = print_missing_packets()

    
    while len(received_sequence_numbers) < total_packets:
        print(f"Current unique packets: {len(received_sequence_numbers)}/{total_packets}")
       
        try:
            poller = select.poll()
            poller.register(mcast_sock, select.POLLIN)
            res = poller.poll(1000)  # 1秒ごとにポーリング

            if res:

                if new_access == 0:
                    program_start_time = time.time()#プログラム開始時のたいむ
                    new_access = +1
                    # 電力監視タスクを開始
                data, addr = mcast_sock.recvfrom(2048)
                now_time = time.time() - program_start_time

                
                if not data:
                    continue

                received_message = json.loads(data.decode('utf-8'))
                
                if "resend_notification" in received_message:
                    resend_list = received_message.get("resend_list", [])
                    print(f"Received resend notification. Resend list: {resend_list}")
                    resend_notification_time = time.time()
                    expected_resend_sequence = iter(resend_list)
                    continue

                if "sequence_number" in received_message:
                    received_sequence_number = received_message["sequence_number"]
                    
                    if received_sequence_number in received_sequence_numbers:
                        duplicate_packets += 1
                        print(f"Duplicate packet detected: {received_sequence_number}")
                    else:
                        received_sequence_numbers.add(received_sequence_number)
                        if received_sequence_number in missing_packets:
                            missing_packets.remove(received_sequence_number)
                            #print(f"Received lost packet: {received_sequence_number}")
                        
                        # Check if this packet is the expected resend packet
                        
                        #######
                        if expected_resend_sequence is not None:
                            try:
                                expected_seq = next(expected_resend_sequence)
                                while expected_seq != received_sequence_number:
                                    if expected_seq in missing_packets:
                                        print(f"Missing resend packet: {expected_seq}")
                                        send_packet_loss([expected_seq])
                                    expected_seq = next(expected_resend_sequence)
                            except StopIteration:
                                expected_resend_sequence = None
                        ##########
                                
                                
                        if last_seq != -1 and received_sequence_number != last_seq + 1:
                            for missing_seq in range(last_seq + 1, received_sequence_number):
                                if missing_seq not in received_sequence_numbers:
                                    event_flag = 1
                                    packet_loss_list.append(missing_seq)
                                    if missing_seq not in missing_packets:
                                        missing_packets.append(missing_seq)
                            #print(f"packet_loss_list:{packet_loss_list}")
                        else:
                            event_flag = 0

                    last_seq = received_sequence_number
                    last_packet_time = time.time()
                else:
                    print(f"decode:{received_message}")
                
                if "end" in received_message:
                    #now_time = time.time() - program_start_time
                    print(f"end_time:{now_time}")
                    event_flag = 0
                    
                    await asyncio.sleep(1)
                    #return

            else:
                await asyncio.sleep(0.1)
            
            
            
            # 再送通知から一定時間経過後、まだ受信できていないパケットを送信
            if resend_notification_time and time.time() - resend_notification_time > 1:  # 1秒の遅延
                
                resend_notification_time = None
                continue
                
            elif (now_time + 1)  <  (time.time() - program_start_time):  # 5秒間パケットが来ない場合
                missing_packets = print_missing_packets()

                if missing_packets:
                    print(f"No packets received for 1 seconds. Sending remaining lost packets: {missing_packets}")
                    send_packet_loss(missing_packets)
                last_packet_time = time.time()  # タイマーをリセット
                continue

        except Exception as e:
            print(f"Error receiving multicast message: {e}")
            await asyncio.sleep(0.1)

    print("Multicast reception completed or timeout reached.")
    print(f"Received {len(received_sequence_numbers)} out of {total_packets} packets.")
    missing_packets = print_missing_packets()
    print(f"Remaining lost packets: {missing_packets}")
    
def send_packet_loss(loss_list):
    if loss_list:
        loss_message = json.dumps(list(loss_list))  # Convert set to list for JSON serialization
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            bytes_sent = s.sendto(loss_message.encode('utf-8'), (SERVER_IP, SERVER_PORT))
            #print(f"Sent packet loss list: {loss_list}")
        except Exception as e:
            print(f"Error sending packet loss list: {e}")
        finally:
            s.close()
    else:
        print("No packet loss to send")
            
def unicast_received():
    global received_sequence_numbers, program_finished,duplicate_packets,unicast_duplicate_packets
    
    unicast_sock = setup_unicast_socket()

    print(f"Listening for unicast on port {UNICAST_PORT}")
    retransmission_loss = []  # Initialize here
    
    select_timeout = 3.0 #初回はながく

    
    start_time = time.time()
    while len(received_sequence_numbers) <= total_packets :  # 最大60秒間受信を試みる
        try:
            ready = select.select([unicast_sock], [], [], select_timeout)
            if ready[0]:
                
                select_timeout = 1.0 #次回から短く
                
                data, addr = unicast_sock.recvfrom(2048)
                received_message = json.loads(data.decode('utf-8'))
                                    
                received_sequence_number = received_message["sequence_number"]
                #print(f"Received unicast packet: {received_sequence_number}")
                if received_sequence_number in received_sequence_numbers:
                    print(f"Duplicate packet detected. Total duplicates")
                else:
                    received_sequence_numbers.add(received_sequence_number)
            else:
                #if missing_packets:
                 #   print("再送中")
                  #  send_packet_loss(missing_packets)
                break
                            
                
        except Exception as e:
            print(f"Error in unicast reception: {e}")
                
    print("unicast ending program.")

    return 0
    
        

def check_timeout():
    global packet_loss_list, program_finished, timeout_thread_running,event_flag
    timeout_thread_running = True
    while not program_finished:
        #time.sleep(1)  # 10秒ごとにチェック
        if program_finished:
            break
        if packet_loss_list and (event_flag == 0):
            send_packet_loss(packet_loss_list)
            packet_loss_list = []
            unicast_received()
    timeout_thread_running = False
    print("check_timeout thread terminated")

async def main():
    global packet_loss_list, program_finished, duplicate_packets, program_start_time,received_count
    
    ssid = "CDSL-A910-11n"
    password = "11n-ky56$HDxgp"


    if connect_wifi(ssid, password):
        machine.Pin(2, machine.Pin.OUT).value(1)
        start_up()

        mcast_sock = setup_multicast_socket()
        
        print("Socket created successfully")
        print("Joined multicast group successfully")
        print("Starting multicast reception...")

        max_retries = 5
        retry_count = 0

        
        while len(received_sequence_numbers) < total_packets:
            await receive_multicast(mcast_sock, 10)  # 1 minute recheck

            print("Multicast reception completed.")
            if packet_loss_list:
                packet_loss_list = []
            
            if not len(received_sequence_numbers) > 749:
                retry_count += 1
                if retry_count >= max_retries:
                    #print(f"Max retries reached. Unable to receive packets: {missing_packets}")
                    #send_packet_loss(missing_packets)  # Send final missing packets
                    break
            else:
                break
        
        completion_time = time.time() - program_start_time
        write_experiment_results_to_csv("yamazaki_resultsE3.csv", completion_time, duplicate_packets)
        # received_count.txtに新しい実験回数を追加
        write_file('received_count.txt', received_count)    

        
        print(f"Reception completed. Total time: {completion_time} seconds")
        print(f"Total duplicate packets: {duplicate_packets}")
        print(f"Total received packets: {len(received_sequence_numbers)} out of {total_packets}")
    
        program_finished = True

        mcast_sock.close()
    else:
        print("Failed to connect to Wi-Fi")
        

        

def receive_experiment_count():
    global SERVER_IP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('239.255.255.251', 50007))
    
    mreq = b''.join([inet_aton('239.255.255.251'), inet_aton('0.0.0.0')])

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            SERVER_IP = addr[0]
            message = json.loads(data.decode('utf-8'))
            if "experiment_count" in message:
                print(f"Received experiment count: {message['experiment_count']}")
                return message['experiment_count']
        except Exception as e:
            print(f"Error receiving experiment count: {e}")
        
        time.sleep(1)  # 1秒待機してから再試行
    sock.close()


def read_file(filename):
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            if lines:
                return int(lines[-1].strip())  # Return the last line as an integer
            else:
                return 0  # Return 0 if the file is empty
    except:
        return 0  # Return 0 if there's an error (e.g., file doesn't exist)

def write_file(filename, content):
    with open(filename, 'a') as f:
        f.write(f"\n{content}")  # Write content on a new line
        
        
def start_up():
    global last_count, received_count
    print("start_up_ok")

    # まず、received_count.txtから最後の実験回数を読み取る
    try:
        with open('received_count.txt', 'r') as f:
            lines = f.readlines()
            last_count = int(lines[-1].strip()) if lines else 0
    except Exception as e:
            print(f"Error receiving experiment count: {e}")
            last_count = 0
    
    print(f"Last recorded experiment count: {last_count}")

    # サーバーから新しい実験回数を受け取る
    received_count = receive_experiment_count()
    print(f"Received experiment count from server: {received_count}")

    

    if received_count == last_count + 1:
        print("正常に次の実験を開始します")
    elif received_count > last_count + 1:
        print(f"警告: 実験回数が飛んでいます。{last_count + 1}から{received_count - 1}までの実験データが欠落している可能性があります")
        for missing_count in range(last_count+1, received_count):
            write_experiment_results_to_csv("yamazaki_resultsE3.csv", "missing", "missing")
    else:
        print(f"エラー: 受信した実験回数({received_count})が前回の実験回数({last_count})以下です")
    
    last_count = received_count
    print(f"実験を開始します。実験回数: {last_count}")
    
def print_missing_packets():
    all_packets = set(range(750))
    missing_packets = all_packets - received_sequence_numbers
    
    return missing_packets  # Return the missing_packets set



if __name__ == "__main__":
    try:
        _thread.start_new_thread(check_timeout, ())
        asyncio.run(main())
    except Exception as e:
        print(f"Error running main: {e}")
    finally:
        program_finished = True
        while timeout_thread_running:
            time.sleep(0.1)
        print("Program execution completed")
    
    machine.Pin(2, machine.Pin.OUT).value(0)

