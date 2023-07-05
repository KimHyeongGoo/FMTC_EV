import os
import pandas as pd
import sys
import datetime
import numpy as np
import time


# YYYY-mm-dd HH:MM:SS -> epoch
def convertTimeToEpoch(_time):
    date_time = "%s.%s.%s %s:%s:%s" %(_time[8:10], _time[5:7], _time[:4], _time[11:13], _time[14:16], _time[17:19])
    pattern = "%d.%m.%Y %H:%M:%S"
    epoch = int (time.mktime(time.strptime(date_time, pattern)))
    return epoch

def fast_func(csv_path, csv_root_dir, csv_output_dir, use_cols):

    _carid = use_cols[0]
    _date = use_cols[1]
    _soc = use_cols[2]
    _slow_charge_con = use_cols[3]
    _fast_charge_con = use_cols[4]
    _b_pack_current = use_cols[5]
    _b_accum_charg_power_quan = use_cols[12]

    skip_rows = 0
    batch_size = 50000
    fast_charging_df_list = []

    while True:
        try:
            df = pd.read_csv(csv_path, low_memory=False, usecols=use_cols, skiprows=range(1, skip_rows), nrows=batch_size)
        except Exception as e:
            print('\n')
            print(csv_path)
            print(e)
            return None

        if len(df) == 0:
            break
        else:
            # 충전 중일 때, 차량 속도는 기록되지 않을 때가 많아서, '차량 속도==0' 조건은 제외했음
            # 또한, 배터리 전류가 nan인 경우는 제외했음 (전류가 nan일 때, 측정된 다른 값들도 오류값을 가짐)
            # 또한, 배터리 전류가 0인 경우는 제외했음 (충전 시작 전이거나, 오류 값)
            # 또한, 누적충전전력이 nan인 경우는 제외했음
            # 또한, SOC=0인 경우는 제외했음 (오류 값)
            # "b_charg_lamp_sts_1 == True" 조건은 생략했음 (충전 중이어도, False인 경우가 있기 때문)
            fast_charging_df_list.append(df.query("%s == 0 and %s == 1 and %s.notna() and %s < 0 and %s.notna() and %s > 0" %(_slow_charge_con, _fast_charge_con, _b_pack_current, _b_pack_current, _b_accum_charg_power_quan, _soc)))
            skip_rows += batch_size

    fast_charging_df = pd.concat(fast_charging_df_list)

    try:
        fast_charging_df.sort_values(by=_date, inplace=True)
        fast_charging_df.reset_index(drop=True, inplace=True)
    except Exception as e:
        print('\n')
        print(csv_path)
        print(e)
        return None

    s_idx = 0 # 급속충전구간 시작점 index
    e_idx = None # 급속충전구간 끝지점 index
    fast_charg_cnt = 1
    for i in range(len(fast_charging_df)-1):
        # 연속된 2개 행 사이의 시간차
        time_diff = convertTimeToEpoch(fast_charging_df.iloc[i+1][_date]) - convertTimeToEpoch(fast_charging_df.iloc[i][_date])

        # 연속된 2개 행 사이의 SOC 차이
        soc_diff = fast_charging_df.iloc[i+1][_soc] - fast_charging_df.iloc[i][_soc]

        # 연속된 2개 행 사이의 누적 충전전력 차이
        power_diff = fast_charging_df.iloc[i+1][_b_accum_charg_power_quan] - fast_charging_df.iloc[i][_b_accum_charg_power_quan]

        # 급속충전데이터의 i~i+1 사이가 30분 이상 끊긴 경우, 또는 SOC가 1% 이상 감소한 경우, 또는 SOC가 5% 이상 증가한 경우, 또는 누적 충전전력이 줄어들거나 5kWh 이상 증가한 경우, 각 급속충전구간의 분리점으로 지정
        if (time_diff >= 30 * 60 or i+1 == len(df)-1) or soc_diff <= -1 or soc_diff >= 5 or power_diff < 0 or power_diff >= 5:
            e_idx = i
            save_df = fast_charging_df.iloc[s_idx:e_idx+1]
            #print(save_df)
            #print(save_df.iloc[-1][_soc],save_df.iloc[0][_soc])

            # 급속충전구간의 충전량(=SOC 증가량)이 5% 이상일 경우 유효한 급속충전구간으로 판단
            if save_df.iloc[-1][_soc] - save_df.iloc[0][_soc] > 5:

                # 급속충전구간으로 지정된 df의 길이가 20이상일 경우 유효한 급속충전구간으로 판단
                if len(save_df) > 20:
                    if not os.path.isdir(csv_output_dir + '/fast_charge/' + str(save_df.iloc[0][_carid])):
                        try: os.makedirs(csv_output_dir + '/fast_charge/' + str(save_df.iloc[0][_carid]))
                        except: pass
                    save_path = csv_output_dir + '/fast_charge/' + str(save_df.iloc[0][_carid]) + '/' + str(save_df.iloc[0][_carid]) + '_' + str(fast_charg_cnt) + '.csv'
                    save_df.to_csv(save_path, index=False)
                    #print(save_path)
                    fast_charg_cnt+=1
            s_idx = i+1

    return None


def discharge_func(csv_path, csv_root_dir, csv_output_dir, use_cols):

    _carid = use_cols[0]
    _date = use_cols[1]
    _soc = use_cols[2]
    _slow_charge_con = use_cols[3]
    _fast_charge_con = use_cols[4]
    _b_pack_current = use_cols[5]
    _b_accum_discharg_power_quan = use_cols[12]
    _car_speed = use_cols[14]
    _charg_lamp_sts = use_cols[16]

    skip_rows = 0
    batch_size = 50000
    discharging_df_list = []

    while True:
        try:
            df = pd.read_csv(csv_path, low_memory=False, usecols=use_cols, skiprows=range(1, skip_rows), nrows=batch_size)
        except Exception as e:
            if str(e).startswith('No columns to parse from file'):
                print('\n')
                print(csv_path)
                print(e)
                return None
            else:
                try:
                    # 22년 4월 데이터에서, v_accel_pedal_depth 필드 없음.. 해당 필드 제외하고 재시도 (이후, SK렌터카로부터 다시 받았음)
                    df = pd.read_csv(csv_path, low_memory=False, usecols=use_cols[:-1], skiprows=range(1, skip_rows), nrows=batch_size)
                except Exception as e:
                    print('\n')
                    print(csv_path)
                    print(e)
                    return None

        if len(df) == 0:
            break
        else:
            # 배터리 전류가 nan인 경우는 제외했음 (전류가 nan일 때, 측정된 다른 값들도 오류값을 가짐)
            # 또한, 누적방전전력이 nan인 경우는 제외했음
            # 또한, SOC=0인 경우는 제외했음 (오류 값)
            discharging_df_list.append(df.query("%s == 0 and %s == 0 and %s == 0 and (%s != 0 or (%s == 0 and %s >= 0)) and %s.notna() and %s.notna() and %s > 0" %(_slow_charge_con, _fast_charge_con, _charg_lamp_sts, _car_speed, _car_speed, _b_pack_current, _b_pack_current, _b_accum_discharg_power_quan, _soc)))
            skip_rows += batch_size

    discharging_df = pd.concat(discharging_df_list)

    try:
        discharging_df.sort_values(by=_date, inplace=True)
        discharging_df.reset_index(drop=True, inplace=True)
    except Exception as e:
        print('\n')
        print(csv_path)
        print(e)
        return None

    s_idx = 0 # 방전구간 시작점 index
    e_idx = None # 방전구간 끝지점 index
    discharg_cnt = 1
    for i in range(len(discharging_df)-1):
        # 연속된 2개 행 사이의 시간차
        time_diff = convertTimeToEpoch(discharging_df.iloc[i+1][_date]) - convertTimeToEpoch(discharging_df.iloc[i][_date])

        # 연속된 2개 행 사이의 SOC 차이
        soc_diff = discharging_df.iloc[i+1][_soc] - discharging_df.iloc[i][_soc]

        # 연속된 2개 행 사이의 누적 방전전력 차이
        power_diff = discharging_df.iloc[i+1][_b_accum_discharg_power_quan] - discharging_df.iloc[i][_b_accum_discharg_power_quan]

        # 방전데이터의 i~i+1 사이가 30분 이상 끊긴 경우, 또는 SOC가 1% 이상 증가한 경우, 또는 SOC가 5% 이상 감소한 경우, 또는 누적 방전전력이 줄어들거나 1kWh 이상 증가한 경우, 각 방전구간의 분리점으로 지정
        if (time_diff >= 30 * 60 or i+1 == len(df)-1) or soc_diff >= 1 or soc_diff <= -5 or power_diff < 0 or power_diff >= 1:
            e_idx = i
            save_df = discharging_df.iloc[s_idx:e_idx+1]
            #print(save_df)
            #print(save_df.iloc[-1][_soc],save_df.iloc[0][_soc])

            # 방전구간의 방전량(=SOC 감소량)이 5% 이상일 경우 유효한 방전구간으로 판단
            if save_df.iloc[0][_soc] - save_df.iloc[-1][_soc] > 5:

                # 방전구간으로 지정된 df의 길이가 20이상일 경우 유효한 방전구간으로 판단
                if len(save_df) > 20:
                    if not os.path.isdir(csv_output_dir + '/discharge/' + str(save_df.iloc[0][_carid])):
                        try: os.makedirs(csv_output_dir + '/discharge/' + str(save_df.iloc[0][_carid]))
                        except: pass
                    save_path = csv_output_dir + '/discharge/' + str(save_df.iloc[0][_carid]) + '/' + str(save_df.iloc[0][_carid]) + '_' + str(discharg_cnt) + '.csv'
                    save_df.to_csv(save_path, index=False)
                    #print(save_path)
                    discharg_cnt+=1
            s_idx = i+1

    return None



def slow_func(csv_path, csv_root_dir, csv_output_dir, use_cols):

    _carid = use_cols[0]
    _date = use_cols[1]
    _soc = use_cols[2]
    _slow_charge_con = use_cols[3]
    _fast_charge_con = use_cols[4]
    _b_pack_current = use_cols[5]
    _b_accum_charg_power_quan = use_cols[12]

    skip_rows = 0
    batch_size = 50000
    slow_charging_df_list = []

    while True:
        try:
            df = pd.read_csv(csv_path, low_memory=False, usecols=use_cols, skiprows=range(1, skip_rows), nrows=batch_size)
        except Exception as e:
            print('\n')
            print(csv_path)
            print(e)
            return None

        if len(df) == 0:
            break
        else:
            # 충전 중일 때, 차량 속도는 기록되지 않을 때가 많아서, '차량 속도==0' 조건은 제외했음
            # 또한, 배터리 전류가 nan인 경우는 제외했음 (전류가 nan일 때, 측정된 다른 값들도 오류값을 가짐)
            # 또한, 배터리 전류가 0인 경우는 제외했음 (충전 시작 전이거나, 오류 값)
            # 또한, 누적충전전력이 nan인 경우는 제외했음
            # 또한, SOC=0인 경우는 제외했음 (오류 값)
            # "b_charg_lamp_sts_1 == True" 조건은 생략했음 (충전 중이어도, False인 경우가 있기 때문)
            slow_charging_df_list.append(df.query("%s == 1 and %s == 0 and %s.notna() and %s < 0 and %s.notna() and %s > 0" %(_slow_charge_con, _fast_charge_con, _b_pack_current, _b_pack_current, _b_accum_charg_power_quan, _soc)))
            skip_rows += batch_size

    slow_charging_df = pd.concat(slow_charging_df_list)

    try:
        slow_charging_df.sort_values(by=_date, inplace=True)
        slow_charging_df.reset_index(drop=True, inplace=True)
    except Exception as e:
        print('\n')
        print(csv_path)
        print(e)
        return None

    s_idx = 0 # 완속충전구간 시작점 index
    e_idx = None # 완속충전구간 끝지점 index
    slow_charg_cnt = 1
    for i in range(len(slow_charging_df)-1):
        # 연속된 2개 행 사이의 시간차
        time_diff = convertTimeToEpoch(slow_charging_df.iloc[i+1][_date]) - convertTimeToEpoch(slow_charging_df.iloc[i][_date])

        # 연속된 2개 행 사이의 SOC 차이
        soc_diff = slow_charging_df.iloc[i+1][_soc] - slow_charging_df.iloc[i][_soc]

        # 연속된 2개 행 사이의 누적 충전전력 차이
        power_diff = slow_charging_df.iloc[i+1][_b_accum_charg_power_quan] - slow_charging_df.iloc[i][_b_accum_charg_power_quan]

        # 완속충전데이터의 i~i+1 사이가 30분 이상 끊긴 경우, 또는 SOC가 1% 이상 감소한 경우, 또는 SOC가 5% 이상 증가한 경우, 또는 누적 충전전력이 줄어들거나 5kWh 이상 증가한 경우, 각 완속충전구간의 분리점으로 지정
        if (time_diff >= 30 * 60 or i+1 == len(df)-1) or soc_diff <= -1 or soc_diff >= 5 or power_diff < 0 or power_diff >= 5:
            e_idx = i
            save_df = slow_charging_df.iloc[s_idx:e_idx+1]
            #print(save_df)
            #print(save_df.iloc[-1][_soc],save_df.iloc[0][_soc])

            # 완속충전구간의 충전량(=SOC 증가량)이 5% 이상일 경우 유효한 완속충전구간으로 판단
            if save_df.iloc[-1][_soc] - save_df.iloc[0][_soc] > 5:

                # 완속충전구간으로 지정된 df의 길이가 20이상일 경우 유효한 완속충전구간으로 판단
                if len(save_df) > 20:
                    if not os.path.isdir(csv_output_dir + '/slow_charge/' + str(save_df.iloc[0][_carid])):
                        try: os.makedirs(csv_output_dir + '/slow_charge/' + str(save_df.iloc[0][_carid]))
                        except: pass
                    save_path = csv_output_dir + '/slow_charge/' + str(save_df.iloc[0][_carid]) + '/' + str(save_df.iloc[0][_carid]) + '_' + str(slow_charg_cnt) + '.csv'
                    save_df.to_csv(save_path, index=False)
                    #print(save_path)
                    slow_charg_cnt+=1
            s_idx = i+1


    return None
