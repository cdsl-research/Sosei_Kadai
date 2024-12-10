import socket
import json
import time
import threading
import select
from collections import defaultdict
import os
from concurrent.futures import ThreadPoolExecutor, as_completed



DMG_IP = '239.255.255.250'
DMG_PORT = 50006
TOTAL_PACKETS = 750
PACKET_SIZE = 1000
SERVER_PORT = 50005
UNICAST_PORT = 50010

count = 0

#タイムアウトの設定
#本当はこっちの方が良い
time_sleep = 1

#送信間隔
delay_per_packet = 0.1

csv_flag = False
# グローバル変数として終了フラグを作成
exit_flag = threading.Event()
send_phase = True

LOCALHOST = socket.gethostbyname(socket.gethostname())
print(f"Local IP: {LOCALHOST}")

packet_loss_dict = defaultdict(set)

def write_Sent_resend_notification_packets_to_csv(lists):
    with open('sousei_Sent_resend_notification_packets.txt', 'a') as file:
        # 最初の空行
        file.write('\n')
        # リストをJSON形式の文字列に変換して書き込む
        json.dump(lists, file)
        file.write('\n')  # 次の書き込みのために改行を追加
    print(f"Resend notification packet list has been written to sousei_Sent_resend_notification_packets.txt")


def send_multicast_message(message, sock, ip, port):
    try:
        sock.sendto(json.dumps(message).encode('utf-8'), (ip, port))
    except socket.error as e:
        if e.errno != 10035:  # WSAEWOULDBLOCK
            raise

def handle_packet_loss(data, addr, chunks):
    global send_phase
    try:
        packet_loss = json.loads(data.decode('utf-8'))
        print(f"PL_list:{packet_loss}")
        ip_address = addr[0]

        if send_phase:
            unicast_resend(chunks, data, addr)
        else:
            packet_loss_dict[ip_address].update(packet_loss)
            print(f"Updated packet loss report for {ip_address}: {packet_loss_dict[ip_address]}")

    except Exception as e:
        print(f"Error in handle_packet_loss: {e}")

def receive_packet_loss(chunks):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', SERVER_PORT))
    print(f"Listening for packet loss reports on port {SERVER_PORT}")

    with ThreadPoolExecutor(max_workers=3) as executor:  # スレッド数は必要に応じて調整
        future_to_data = {}
        while not exit_flag.is_set():
            try:
                ready = select.select([s], [], [], 10.0)
                if ready[0]:
                    data, addr = s.recvfrom(2048)
                    future = executor.submit(handle_packet_loss, data, addr ,chunks)
                    future_to_data[future] = (data, addr)
                else:
                    print("No data received in the last 5 seconds")

                # 完了したタスクの処理
                for future in as_completed(future_to_data):
                    data, addr = future_to_data[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f'Task generated an exception: {exc}')
                    del future_to_data[future]

            except Exception as e:
                print(f"Error in receive_packet_loss: {e}")

    s.close()


def unicast_resend(chunks, data, addr):
    #global unique_losses, sorted_duplicates
    no_new_reports_count = 1
    max_no_new_reports = 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setblocking(False)

    # ユニキャスト再送信
    #send_unicast_notification(sock, ip, losses)
    time.sleep(delay_per_packet)
    #time.sleep(time_sleep)
    successfully_sent = []
    ip = addr[0]

    packet_loss = json.loads(data.decode('utf-8'))

    for seq_num in packet_loss:
        if 0 <= seq_num < TOTAL_PACKETS:
            chunk = chunks[seq_num].ljust(PACKET_SIZE, '\0')
            message = {
                "sequence_number": seq_num,
                "data": chunk,
                "resend": True
            }
            sock.sendto(json.dumps(message).encode('utf-8'), (ip, UNICAST_PORT))
            #print(f"Unicast resent packet {seq_num} to {ip}")
            successfully_sent.append(seq_num)
            time.sleep(delay_per_packet)


def resend_lost_packets(chunks):
    global csv_flag
    resend_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    resend_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    resend_sock.setblocking(False)

    all_lost_packets = set()
    for losses in packet_loss_dict.values():
        all_lost_packets.update(losses)

    if all_lost_packets:
        resend_notification = {
            "resend_notification": True,
            "resend_list": sorted(list(all_lost_packets))
        }
        send_multicast_message(resend_notification, resend_sock, DMG_IP, DMG_PORT)
        if not csv_flag:
            write_Sent_resend_notification_packets_to_csv(sorted(list(all_lost_packets)))
            csv_flag = True
        print(f"Sent resend notification for packets: {list(all_lost_packets)}")

        # 適応的な待機時間の実装
        start_time = time.time()
        packet_loss_reported = False
        while time.time() - start_time < time_sleep*5:
            if any(packet_loss_dict.values()):
                packet_loss_reported = True
                break
            time.sleep(0.1)  # 短い間隔でチェック

        if not packet_loss_reported:
            print("No immediate packet loss reported. Extending wait time.")
            time.sleep(time_sleep*2)  # 追加の待機時間

        for seq_num in sorted(all_lost_packets):
            if 0 <= seq_num < TOTAL_PACKETS:
                chunk = chunks[seq_num].ljust(PACKET_SIZE, '\0')
                message = {
                    "sequence_number": seq_num,
                    "data": chunk,
                    "resend": True
                }
                send_multicast_message(message, resend_sock, DMG_IP, DMG_PORT)
                print(f"Resent packet {seq_num}")
                time.sleep(delay_per_packet)

        # 再送信したパケットを全てのクライアントのパケットロスリストから削除
        for ip_address in packet_loss_dict:
            packet_loss_dict[ip_address] -= all_lost_packets
        # all_lost_packetsの内容を消去
        all_lost_packets.clear()

    print("Finished resending lost packets")
    return list(all_lost_packets)

def resend_specific_packets(chunks, packet_list):
    resend_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    resend_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    resend_sock.setblocking(False)

    for seq_num in packet_list:
        if 0 <= seq_num < TOTAL_PACKETS:
            chunk = chunks[seq_num].ljust(PACKET_SIZE, '\0')
            message = {
                "sequence_number": seq_num,
                "data": chunk,
                "resend": True
            }
            send_multicast_message(message, resend_sock, DMG_IP, DMG_PORT)
            print(f"最終再送信: パケット {seq_num}")
            time.sleep(delay_per_packet)

def main():
    global send_phase

    chunks = []
    FILE_NAME = 'sendingFile_750KB.txt'
    with open(FILE_NAME, 'r') as f:
        for line in f:
            line = line.strip()
            chunks.append(line[:PACKET_SIZE])

    receive_thread = threading.Thread(target=receive_packet_loss, args=(chunks,), daemon=True)
    receive_thread.start()



    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setblocking(False)

    initial_message = {"total_packets": TOTAL_PACKETS}
    send_multicast_message(initial_message, sock, DMG_IP, DMG_PORT)
    print(f"Sent initial message: {initial_message}")

     # 送信開始時間を記録
    start_time = time.time()

    for i in range(TOTAL_PACKETS):
        chunk = chunks[i].ljust(PACKET_SIZE, '\0')
        message = {
            "sequence_number": i,
            "data": chunk
        }
        send_multicast_message(message, sock, DMG_IP, DMG_PORT)
        print(f"Sent packet {i}")
        time.sleep(delay_per_packet)
    send_phase = False
    end_message = {"end": True}
    send_multicast_message(end_message, sock, DMG_IP, DMG_PORT)


     # 送信終了時間を記録
    end_time = time.time()

    # 送信にかかった時間を計算
    transmission_time = end_time - start_time
    print(f"Total transmission time: {transmission_time:.2f} seconds")

    last_resent_packets = []
    final_resend_attempts = 0
    max_final_resend_attempts = 10  # Maximum number of final resend attempts

    while True:
        print("Waiting for packet loss reports...")
        time.sleep(time_sleep)

        if not any(packet_loss_dict.values()):
            if last_resent_packets:
                print(f"Final resend attempt for packets: {last_resent_packets}")
                resend_specific_packets(chunks, last_resent_packets)
                final_resend_attempts += 1

                if final_resend_attempts >= max_final_resend_attempts:
                    print(f"Max final resend attempts ({max_final_resend_attempts}) reached. Ending transmission.")
                    break

                time.sleep(time_sleep*2)  # Wait after final resend
                continue  # Go back to the start of the loop to check for packet loss again
            else:
                print("No packet loss reported. Transmission complete.")
                #break

        last_resent_packets = resend_lost_packets(chunks)
        #time.sleep(time_sleep)

    exit_flag.set()
    receive_thread.join()

def start_server(host, port):
    s = socket.socket()
    s.bind((host, port))
    s.listen(1)
    print(f"Listening on {host}:{port}")

    while True:
        conn, addr = s.accept()
        print(f"Connected by {addr}")

        # クライアントからのメッセージを受信
        data = conn.recv(1024).decode()
        print(f"Received: {data}")

        # クライアントにメッセージを送信
        conn.send("Hello from Python!".encode())

        if data:
            # クライアントからの2つ目のメッセージを受信
            data = conn.recv(1024).decode()
            print(f"Received: {data}")
            conn.close()
            return

def read_experiment_count():
    filename = 'sousei_experiment_count.txt'
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write("1\n")
        return 1

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            if lines:
                return int(lines[-1].strip())
            else:
                # ファイルが空の場合
                with open(filename, 'w') as f:
                    f.write("1\n")
                return 1
    except ValueError:
        # ファイルの内容が不正な場合
        with open(filename, 'w') as f:
            f.write("1\n")
        return 1


def write_experiment_count(count):
    with open('sousei_experiment_count.txt', 'a') as f:
        f.write(f"{count}\n")


def start_up():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    current_count = read_experiment_count()

    message = {
        "experiment_count": current_count
    }

    try:
        sock.sendto(json.dumps(message).encode('utf-8'), ('239.255.255.251', 50007))
        print(f"Sent experiment count {current_count} to {DMG_IP}:{DMG_PORT}")
    except Exception as e:
        print(f"Error sending experiment count: {e}")
    finally:
        sock.close()

    write_experiment_count(current_count + 1)

    # マルチキャスト実験の実行（ここに実験のコードを追加）
    time.sleep(5)  # 実験の代わりに5秒待機



if __name__ == "__main__":
    start_up()
    main()