# Sosei_Kadai

# 用途・目的

これらのファイルはマルチキャストでの送信に関するプログラムである．
クライアントはmain.py，サーバはserver.pyである．これらのプログラムの説明をする．サーバはsendingFile_100KB.txtから115bytesに分割し，891個のパケットを生成する．そのあと，クライアントに向けてマルチキャストをする．もしパケットロスがあれば，再送信を行う．

# 今回使用したクライアントとサーバのハードウェア
クライアントにはESP32を使用した．クライアントにはmain.pyがある．

サーバには，ESXiを用い，仮想マシンを作成した．サーバにはserver.pyとsendingFile_100KB.txtがある．



# プログラムの紹介
## main.py

サーバからクライアントに891個のパケットを受信するプログラムである．


## server.py 

クライアントに対し，マルチキャストでsendingFile_100kB.txtから115bytesのパケットに分割し，それらにシーケンス番号を付け，891個のパケットを送信するプログラムである． またパケットロスが発生した場合，2種類の方法で再送信を行う．891個のパケットを送信中であればユニキャストで，それ以降であればマルチキャストで再送信を行う．

# 使用言語
クライアントはMicroPython言語で記述されている． サーバはPythonで記述されている．

# 実行方法

クライアントはESP32を使い，MicroPythonのファームウェアはv1.24.0を使用している．プログラムの記述にはThonnyを用いた．

サーバはESXiに仮想環境を建て，そこにserver.pyとsendingFile_100kB.txtを置いている．クライアントにはmain.pyを置いている．

まず，クライアントを起動し，Wi-Fi接続を行う．ESP32が以下の写真の通りになればWi-Fi接続が完了している．

![esp32画像](https://github.com/user-attachments/assets/a8c6abe7-ec61-4ce2-b8d3-9c96b537af51)

その後，仮想環境でPythonファイルを下記の方法からpowershell等で実行する．

~~~
Python3 server.py
~~~

# 注意点
Wi-Fi接続に必要なssidとpasswordを設定する． マルチキャストアドレスとポートは適切なものを設定する．

# クライアントの実行結果
結果の一部を抜粋する．
main.pyの結果は以下の通りである．

![image](https://github.com/user-attachments/assets/84d0439f-a873-4f1d-b78a-83ff21496ce8)

・

・

・

![image](https://github.com/user-attachments/assets/b2934e29-fcd7-4fb3-97f9-0882b634bdba)





# サーバの実行結果
結果の一部を抜粋する．
server.pyは以下の通りである．

![image](https://github.com/user-attachments/assets/9f8d3ac5-d9fa-4366-bcdc-2e445daaa1b8)

・

・

・

![image](https://github.com/user-attachments/assets/abc68209-c6d9-40bf-9ec2-22591056b120)
