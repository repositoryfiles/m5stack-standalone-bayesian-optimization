"""Core2 UIFlow2 MicroPython: stage-1 3s automatic PD gain search.
Copy to Core2 as main.py after editing Wi-Fi password.
"""
import M5, time, math, gc, json, network, requests
from machine import I2C, Pin
from unit import Roller485Unit

SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
SERVER = 'http://192.168.137.1:8000'
MAX_TRIALS = 180
PERIOD_US = 10000
TRIAL_MS = 3000
RISE_LIMIT_MS = 1000
EVAL_START_MS = 1000
TAU = 0.5
MAX_CURRENT = 200
START_MIN, START_MAX = 5.0, 8.0
BUMPER_MIN, BUMPER_MAX = 5.0, 9.0
RELEASE_ANGLE, STOP_ANGLE, SAFETY_ANGLE = 4.5, 6.0, 10.0
STILL_MS, STILL_GYRO, STILL_SPAN = 400, 2.0, 0.5
WAIT_START_MS, WAIT_BUMPER_MS = 30000, 15000
CYAN, YELLOW, GREEN, BLUE, RED, WHITE = 0x00FFFF, 0xFFFF00, 0x00FF00, 0x0000FF, 0xFF0000, 0xFFFFFF
motor1 = None
motor2 = None


def display(color):
    M5.Lcd.fillScreen(color)


def button_a():
    while True:
        M5.update()
        if M5.BtnA.wasPressed():
            break
        time.sleep_ms(20)
    while True:
        M5.update()
        if not M5.BtnA.isPressed():
            break
        time.sleep_ms(10)
    time.sleep_ms(100)
    M5.update()


def stop_motors():
    for m in (motor1, motor2):
        if m is not None:
            try:
                m.set_motor_max_current(0)
            except Exception as e:
                print('Current stop:',repr(e))
    for m in (motor1, motor2):
        if m is not None:
            try:
                m.set_motor_output_state(0)
            except Exception as e:
                print('Output stop:',repr(e))


def connect_wifi():
    display(CYAN)
    w = network.WLAN(network.STA_IF)
    # Keep an already connected interface intact (UIFlow2 Wi-Fi state).
    try:
        already = w.isconnected()
    except OSError:
        w.active(True)
        time.sleep_ms(300)
        already = w.isconnected()
    if not already:
        w.active(True)
        time.sleep_ms(300)
        w.connect(SSID, PASSWORD)
        start = time.ticks_ms()
        while not w.isconnected():
            if time.ticks_diff(time.ticks_ms(),start) > 15000:
                raise RuntimeError('Wi-Fi timeout')
            time.sleep_ms(200)
    print('Wi-Fi:',w.ifconfig())
    return w


def get_gains():
    for attempt in range(3):
        response = None
        try:
            response = requests.get(SERVER+'/gains',timeout=5)
            if response.status_code != 200:
                raise RuntimeError('GET status '+str(response.status_code))
            return json.loads(response.text)
        except OSError as e:
            print('GET retry:',repr(e))
            if attempt == 2:
                raise
            time.sleep_ms(1500)
        finally:
            if response is not None:
                response.close()


def post_result(data):
    trial = data['trial']
    for attempt in range(3):
        response = None
        try:
            response = requests.post(SERVER+'/result',data=json.dumps(data),
                headers={'Content-Type':'application/json'},timeout=5)
            if response.status_code != 200:
                raise RuntimeError('POST status '+str(response.status_code)+' '+response.text)
            answer = json.loads(response.text)
            if answer.get('completed') == trial and answer.get('status') in ('ok','duplicate'):
                return
            raise RuntimeError('POST response '+str(answer))
        except OSError as e:
            print('POST retry:',repr(e))
            time.sleep_ms(1500)
            try:
                status = get_gains()
                if status.get('trial') == trial+1 or (status.get('status') == 'finished' and status.get('trials') == trial):
                    print('POST confirmed by GET')
                    return
                if status.get('trial') != trial:
                    raise RuntimeError('Server state uncertain '+str(status))
            except OSError as check_error:
                print('Confirmation failed:',repr(check_error))
            if attempt == 2:
                raise
        finally:
            if response is not None:
                response.close()
    raise RuntimeError('POST not confirmed')


def initialize_motors():
    global motor1,motor2
    i2c = I2C(0,scl=Pin(33),sda=Pin(32),freq=100000)
    devices = i2c.scan()
    print('I2C:',devices)
    if 0x64 not in devices or 0x65 not in devices:
        raise RuntimeError('Motor not found')
    motor1 = Roller485Unit(i2c,address=0x64,mode=Roller485Unit.I2C_MODE)
    motor2 = Roller485Unit(i2c,address=0x65,mode=Roller485Unit.I2C_MODE)
    for m in (motor1,motor2):
        m.set_motor_output_state(0)
        m.set_motor_mode(3)
        m.set_motor_max_current(0)


def calibrate():
    display(YELLOW)
    total_angle = 0.0
    total_gyro = 0.0
    for i in range(200):
        ax,ay,az = M5.Imu.getAccel()
        gx,gy,gz = M5.Imu.getGyro()
        total_angle += math.degrees(math.atan2(ay,az))
        total_gyro += gx
        time.sleep_ms(10)
    offsets = total_angle/200.0,total_gyro/200.0
    print('Offsets:',offsets)
    return offsets


def measure_still(angle_offset,gyro_bias):
    angles=[]
    max_gyro=0.0
    start=time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(),start) < STILL_MS:
        M5.update()
        if M5.BtnA.wasPressed():
            raise RuntimeError('Button A stop')
        ax,ay,az=M5.Imu.getAccel()
        gx,gy,gz=M5.Imu.getGyro()
        angles.append(math.degrees(math.atan2(ay,az))-angle_offset)
        max_gyro=max(max_gyro,abs(gx-gyro_bias))
        time.sleep_ms(10)
    theta=sum(angles)/len(angles)
    still=max_gyro <= STILL_GYRO and max(angles)-min(angles) <= STILL_SPAN
    return theta,still


def wait_angle(angle_offset,gyro_bias,minimum,maximum,timeout_ms,label):
    start=time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(),start) < timeout_ms:
        theta,still=measure_still(angle_offset,gyro_bias)
        if still and minimum <= abs(theta) <= maximum:
            print(label,round(theta,3))
            return theta
    raise RuntimeError(label+' timeout')


def trial_run(angle_offset,gyro_bias,initial_theta,kp,kd,trial):
    ax,ay,az=M5.Imu.getAccel()
    angle=math.degrees(math.atan2(ay,az))
    reason='Time limit'
    released=False
    rise_ms=-1
    min_theta=max_theta=final_theta=initial_theta
    min_abs_theta=abs(initial_theta)
    cycles=eval_samples=upright_samples=0
    sum_sq=0.0
    max_command=max_dt=0
    gc.collect()
    gc.disable()
    start_us=time.ticks_us()
    try:
        motor1.set_motor_max_current(0)
        motor2.set_motor_max_current(0)
        motor1.set_motor_output_state(1)
        motor2.set_motor_output_state(1)
        display(GREEN)
        start_us=time.ticks_us()
        last_us=start_us
        next_us=time.ticks_add(start_us,PERIOD_US)
        while True:
            while time.ticks_diff(next_us,time.ticks_us()) > 0:
                pass
            now=time.ticks_us()
            dt_us=time.ticks_diff(now,last_us)
            last_us=now
            max_dt=max(max_dt,dt_us)
            if dt_us <= 0 or dt_us > 20000:
                reason='Cycle timeout'
                break
            M5.update()
            if M5.BtnA.wasPressed():
                reason='Button A stop'
                break
            ax,ay,az=M5.Imu.getAccel()
            gx,gy,gz=M5.Imu.getGyro()
            gx -= gyro_bias
            dt=dt_us/1000000.0
            accel_angle=math.degrees(math.atan2(ay,az))
            alpha=TAU/(TAU+dt)
            angle=alpha*(angle+gx*dt)+(1-alpha)*accel_angle
            theta=angle-angle_offset
            final_theta=theta
            min_theta=min(min_theta,theta)
            max_theta=max(max_theta,theta)
            min_abs_theta=min(min_abs_theta,abs(theta))
            cycles += 1
            elapsed_us=time.ticks_diff(now,start_us)
            elapsed_ms=elapsed_us/1000.0
            if abs(theta) >= SAFETY_ANGLE:
                reason='Angle safety limit'
                break
            if not released and abs(theta) <= RELEASE_ANGLE:
                released=True
                rise_ms=round(elapsed_ms)
            if released and abs(theta) >= STOP_ANGLE:
                reason='Fall'
                break
            if not released and elapsed_ms >= RISE_LIMIT_MS:
                reason='Rise failure'
                break
            if elapsed_us >= EVAL_START_MS*1000 and elapsed_us <= TRIAL_MS*1000:
                sum_sq += theta*theta
                eval_samples += 1
                if abs(theta) < 2.0:
                    upright_samples += 1
            u=-kp*theta-kd*gx
            u=max(-MAX_CURRENT,min(MAX_CURRENT,u))
            current=int(u)
            max_command=max(max_command,abs(current))
            motor1.set_motor_max_current(current)
            motor2.set_motor_max_current(-current)
            if elapsed_us >= TRIAL_MS*1000:
                reason='Time limit'
                break
            next_us=time.ticks_add(next_us,PERIOD_US)
    finally:
        stop_motors()
        gc.enable()
    elapsed_ms=round(time.ticks_diff(time.ticks_us(),start_us)/1000.0)
    valid=(reason=='Time limit' and released and eval_samples>=190)
    rms=math.sqrt(sum_sq/eval_samples) if valid else -1.0
    return {'trial':trial,'kp':kp,'kd':kd,'reason':reason,
            'elapsed_ms':elapsed_ms,'samples':cycles,'initial_theta':initial_theta,
            'final_theta':final_theta,'min_theta':min_theta,'max_theta':max_theta,
            'min_abs_theta':min_abs_theta,'rms':rms,'eval_samples':eval_samples,
            'upright_ms':upright_samples*PERIOD_US/1000.0,'rise_ms':rise_ms,
            'max_command':max_command,'max_dt_ms':max_dt/1000.0,'released':released}


def run():
    M5.begin()
    display(CYAN)
    initialize_motors()
    connect_wifi()
    print('Upright; press A to calibrate')
    button_a()
    angle_offset,gyro_bias=calibrate()
    print('Place against bumper; press A to start')
    button_a()
    for n in range(1,MAX_TRIALS+1):
        gains=get_gains()
        if gains.get('status')=='finished':
            print('Server finished')
            break
        if gains.get('status')!='ready' or gains.get('trial')!=n:
            raise RuntimeError('Server trial mismatch '+str(gains))
        kp=float(gains['kp'])
        kd=float(gains['kd'])
        print('Trial',n,'Kp',kp,'Kd',kd)
        display(BLUE)
        initial_theta=wait_angle(angle_offset,gyro_bias,START_MIN,START_MAX,WAIT_START_MS,'Start')
        result=trial_run(angle_offset,gyro_bias,initial_theta,kp,kd,n)
        print('Result:',result)
        # Do not proceed until both motors are off and the body is stationary at a bumper.
        display(YELLOW)
        settled=wait_angle(angle_offset,gyro_bias,BUMPER_MIN,BUMPER_MAX,WAIT_BUMPER_MS,'Bumper')
        print('Bumper:',settled)
        post_result(result)
        print('Saved',n,'reason',result['reason'])
        if result['reason'] in ('Button A stop','Cycle timeout','Angle safety limit'):
            raise RuntimeError('Safety stop: '+result['reason'])
        time.sleep_ms(300)
    display(WHITE)
    print('Stage 1 complete')


try:
    run()
except Exception as e:
    print('Stopped:',repr(e))
    try:
        display(RED)
    except Exception:
        pass
finally:
    stop_motors()
    gc.enable()
while True:
    time.sleep_ms(200)
