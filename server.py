import eventlet
import socketio

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio)

all_player = [['',''] for i in range(10)] # 10 個房間的玩家
play_ready = [[-1,-1] for i in range(10)] # 已經準備開始
player_best_score = [['',''] for i in range(10)] # 玩家最佳分數
player_win = [['',''] for i in range(10)] # 玩家勝場數
player_lose = [['',''] for i in range(10)] # 玩家敗場數
player_tie = [['',''] for i in range(10)] # 玩家平手數

lock_room = [False for i in range(10)] # 房間開始遊戲後不可進

gameover_count = [0 for i in range(10)] # 玩家掛掉紀錄
name_to_sid = {}
uid_to_sid = {}

@sio.event
def connect(sid, environ):
    sio.enter_room(sid, sid)
    sio.emit('lock_room',{'lock_room_list': lock_room}, room=sid)
    print('connect ', sid)

@sio.event
def register_player(sid, data): # 玩家進入房間
    uid = data['uid']
    room_num = data['room_num']
    global name_to_sid, uid_to_sid
    
    # 若房間遊戲進行中，不准進入
    if lock_room[room_num]:
        print(f"Room {room_num} is locked. Blocked {uid}")
        sio.emit('room_locked_error', {'msg': 'Game in progress'}, room=sid)
        return

    # 1. 檢查玩家是否已經在任何房間裡，若有則先清理
    for i in range(len(all_player)):
        if uid in all_player[i]:
            try:
                old_idx = all_player[i].index(uid)
                if old_idx < 2:
                    all_player[i][old_idx] = ''
                    play_ready[i][old_idx] = -1
                else:
                    all_player[i].remove(uid)
                if all_player[i][0] == '' and all_player[i][1] == '':
                    lock_room[i] = False
                    gameover_count[i] = 0
            except ValueError:
                pass

    # 2. 紀錄新的連線關係
    name_to_sid[sid] = uid 
    uid_to_sid[uid] = sid
    
    # 3. 進入目標房間 (前兩名為玩家，其餘為觀戰)
    p_idx = -1
    if all_player[room_num][0] == '':
        all_player[room_num][0] = uid
        p_idx = 0
    elif all_player[room_num][1] == '':
        all_player[room_num][1] = uid
        p_idx = 1
    else:
        all_player[room_num].append(uid)
        p_idx = len(all_player[room_num]) - 1
    
    # 更新統計資訊
    if p_idx != -1 and p_idx < 2:
        player_best_score[room_num][p_idx] = data['best_score']
        player_win[room_num][p_idx] = data['player_win']
        player_lose[room_num][p_idx] = data['player_lose']
        player_tie[room_num][p_idx] = data['player_tie']

    sio.enter_room(sid, room_num)
    sio.emit('in_room', {
        'player_name': all_player[room_num],
        'ready_level': play_ready[room_num],
        'player_num': len(all_player[room_num]),
        'best_score': player_best_score[room_num],
        'player_win': player_win[room_num],
        'player_lose': player_lose[room_num],
        'player_tie': player_tie[room_num],
        'player_index': p_idx
    }, room=room_num)

@sio.event
def leave_room(sid,data): # 玩家退出房間
    uid = data['uid']
    room_num = data['room_num']
    global name_to_sid, uid_to_sid
    
    try:
        player_index = all_player[room_num].index(uid)
        if player_index < 2:
            all_player[room_num][player_index] = ''
            play_ready[room_num][player_index] = -1
            player_best_score[room_num][player_index] = ''
            player_win[room_num][player_index] = ''
            player_lose[room_num][player_index] = ''
            player_tie[room_num][player_index] = ''
        else:
            all_player[room_num].remove(uid)
            
    except ValueError:
        pass
    
    sio.leave_room(sid, room_num)
    if all_player[room_num][0] == '' and all_player[room_num][1] == '': # 房間沒人了
        lock_room[room_num] = False
        gameover_count[room_num] = 0
        sio.emit('lock_room',{'lock_room_list': lock_room})
    
    sio.emit('in_room', {
        'player_name': all_player[room_num],
        'ready_level': play_ready[room_num],
        'player_num': len(all_player[room_num]),
        'best_score': player_best_score[room_num],
        'player_win': player_win[room_num],
        'player_lose': player_lose[room_num],
        'player_tie': player_tie[room_num],
        'player_index': -1 # Leave room doesn't need to specify who joined
    }, room=room_num)

@sio.event
def room_ready(sid, data): # 房間準備開始
    uid = data['uid']
    room_num = data['room_num']
    p_idx = data['player_index']
    if p_idx < 2:
        play_ready[room_num][p_idx] = data['level']
        if play_ready[room_num][0] != -1 and play_ready[room_num][1] != -1:
            lock_room[room_num] = True
            sio.emit('lock_room',{'lock_room_list': lock_room})
        sio.emit('play_ready',{'ready_level': play_ready[room_num]}, room=room_num)

@sio.event
def send_random_block(sid,data): # 傳送方塊種子碼
    room_num = data['room_num']
    sio.emit('get_random_block',{'random_block': data['random_block']}, room=room_num)

@sio.event
def tetris_server_block(sid, data):
    room_num = data['room_num']
    sio.emit('tetris_client_block', data, room=room_num, skip_sid=sid)

@sio.event
def gameover(sid,data):
    room_num = data['room_num']
    gameover_count[room_num] = gameover_count[room_num] + 1
    # 只要有人掛掉就廣播，不論是不是雙方都掛掉
    sio.emit('client_gameover', data, room=room_num, skip_sid=sid)
    
    if gameover_count[room_num] >= 2: # 雙方都掛掉，遊戲重置房間狀態
        play_ready[room_num] = [-1,-1]
        lock_room[room_num] = False
        gameover_count[room_num] = 0
        sio.emit('lock_room',{'lock_room_list': lock_room})

@sio.event
def disconnect(sid):
    if sid in name_to_sid:
        uid = name_to_sid.pop(sid)
        if uid_to_sid.get(uid) == sid:
            print(uid, '斷線（主連線）')
            del uid_to_sid[uid]
            for i in range(len(all_player)):
                if uid in all_player[i]:
                    room_num = i
                    player_index = all_player[room_num].index(uid)
                    if player_index < 2:
                        all_player[room_num][player_index] = ''
                        play_ready[room_num][player_index] = -1
                        player_best_score[room_num][player_index] = ''
                        player_win[room_num][player_index] = ''
                        player_lose[room_num][player_index] = ''
                        player_tie[room_num][player_index] = ''
                    else:
                        all_player[room_num].remove(uid)
                    sio.emit('in_room', {
                        'player_name': all_player[room_num],
                        'ready_level': play_ready[room_num],
                        'player_num': len(all_player[room_num]),
                        'best_score': player_best_score[room_num],
                        'player_win': player_win[room_num],
                        'player_lose': player_lose[room_num],
                        'player_tie': player_tie[room_num]
                    }, room=room_num)
                    if all_player[room_num][0] == '' and all_player[room_num][1] == '': 
                        lock_room[room_num] = False
                        gameover_count[room_num] = 0
                        sio.emit('lock_room',{'lock_room_list': lock_room})
                    break
    print('disconnect ', sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)