# Sosei_Kadai

# 用途・目的

これらのファイルはマルチキャストでの送信に関するプログラムである．
クライアントはclient.py，サーバはserver.pyである．これらのプログラムの説明をする．サーバはsendingFile_100KB.txtから115bytesに分割し，891個のパケットを生成する．そのあと，クライアントに向けてマルチキャストをする．もしパケットロスがあれば，再送信を行う．

# 今回使用したクライアントとサーバのハードウェア
クライアントにはESP32を使用した．クライアントにはclient.pyがある．

サーバには，ESXiを用い，仮想マシンを作成した．サーバにはserver.pyとsendingFile_100KB.txtがある．



# プログラムの紹介
## client.py

サーバからクライアントに891個のパケットを受信するプログラムである．


## server.py 

クライアントに対し，マルチキャストでsendingFile_100kB.txtから115bytesのパケットに分割し，それらにシーケンス番号を付け，891個のパケットを送信するプログラムである． またパケットロスが発生した場合，2種類の方法で再送信を行う．891個のパケットを送信中であればユニキャストで，それ以降であればマルチキャストで再送信を行う．

# 使用言語
クライアントはMicroPython言語で記述されている． サーバはPythonで記述されている．

# 実行方法

クライアントはESP32を使い，MicroPythonのファームウェアはv1.24.0を使用している．プログラムの記述にはThonnyを用いた．

サーバはESXiに仮想環境を建て，そこにserver.pyとsendingFile_100kB.txtを置いて実行している．仮想環境でPythonファイルを実行する時は，下記の方法からpowershell等で実行する．

~~~
Python3 server.py
~~~

# 注意点
Wi-Fi接続に必要なssidとpasswordを設定する． マルチキャストアドレスとポートは適切なものを設定する．

# クライアントの実行結果
結果の一部を抜粋する．
client.pyの結果は以下の通りである．

![image](https://github.com/user-attachments/assets/9be1948b-4cc2-4824-bd64-043e60d6e624)
下の図は終わった際の結果
![image](https://github.com/user-attachments/assets/4ff2c7e4-5fad-4a70-a382-1573e0f1f870)




# サーバの実行結果
結果の一部を抜粋する．
server.pyは以下の通りである．

![image](https://github.com/user-attachments/assets/1d56cdfe-806b-4e83-9527-5512837c6272)
下の図は終わった際の結果
![image](https://github.com/user-attachments/assets/da1db8bb-b072-4d05-91bb-f937dfa58b8c)
