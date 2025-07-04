import yaml
import re
import logging
import json

from .utils import ms_to_pace, dist_time_to_ms, get_pace_range, pace_to_ms
from .workout import Target, Workout, WorkoutStep
from planner.garmin_client import GarminClient

CLEAN_KEYS = ['author', 'createdDate', 'ownerId', 'shared', 'updatedDate']

def cmd_import_workouts(args):
    logging.info('importing workouts from ' + args.workouts_file)
    existing_workouts = []

    client = GarminClient(args.oauth_folder)
    if not args.dry_run:
        if args.replace:
            existing_workouts = client.list_workouts()

    for workout in import_workouts(args.workouts_file, args.name_filter):
        if args.treadmill or workout.workout_name.strip().endswith('(T)'):
            workout.dist_to_time()

        if args.dry_run:
            print(json.dumps(workout.garminconnect_json()))
        else:
            logging.info('creating workout: ' + workout.workout_name)
            workouts_to_delete = []
            id_to_replace = None
            if args.replace:
                for wo in existing_workouts:
                    if wo['workoutName'] == workout.workout_name:
                        id_to_replace = wo['workoutId']
            if id_to_replace != None:
                client.update_workout(id_to_replace, workout)
            else:
                client.add_workout(workout)

    return None

def cmd_export_workouts(args):

    def clean(wo_dict):
        if isinstance(wo_dict, list):
            for ldict in wo_dict:
                clean(ldict)
        elif isinstance(wo_dict, dict):
            keys = list(wo_dict.keys())
            for k in keys:
                v = wo_dict[k]
                if k in CLEAN_KEYS or v == None or v == 'null':
                    del wo_dict[k]
                elif isinstance(v, dict) or isinstance(v, list):
                    final_size = clean(v)
                    if final_size == 0:
                        del wo_dict[k]
        return len(wo_dict)

    client = GarminClient(args.oauth_folder)
    workout_ids = client.list_workouts()

    if args.name_filter:
        filtered = []
        for workout in workout_ids:
            if re.search(args.name_filter, workout['workoutName']):
                filtered.append(workout)
        workout_ids = filtered

    workouts = []
    for wid in workout_ids:
        workout = client.get_workout(wid['workoutId'])
        if args.clean:
            clean(workout)
        workouts.append(workout)

    formatted_output = ''
    export_format = args.format

    # If export format was not indicated in the command line, the file extension can decide it
    file_extension = args.export_file.split('.')[-1].upper() if '.' in args.export_file else None
    if not export_format and file_extension:        
        if file_extension in ['JSON', 'JSN']:
            export_format = 'JSON'
        elif file_extension in ['YAML', 'YML']:
            export_format = 'YAML'

    if not export_format or export_format == 'JSON':
        formatted_output = json.dumps(workouts, indent=2)
    elif export_format == 'YAML':
        formatted_output = yaml.dump(workouts)

    if args.export_file != '':
        print('exporting workouts to file '+ args.export_file)
        f = open(args.export_file, 'w')
        f.write(formatted_output)
        f.close()
    else:
        print(formatted_output)

    return None

def cmd_delete_workouts(args):
    valid_ids = []
    client = GarminClient(args.oauth_folder)
    if args.workout_ids:
        if ',' in args.workout_ids:
            workout_ids = args.workout_ids.split(',')
        else:
            workout_ids = [args.workout_ids]

        # filter out invalid workout IDs
        for workout_id in workout_ids:
            if not re.match(r'^\d{9}$', workout_id):
                logging.warning(f'ignoring invalid workout id "{workout_id}". Must be 9 digit number.')
            else:
                valid_ids.append(workout_id)

    if args.name_filter:
        logging.info(f'getting list of workouts.')
        workouts_list = client.list_workouts()
        for workout in workouts_list:
            if re.search(args.name_filter, workout['workoutName']):
                logging.info(f'found workout named "{workout["workoutName"]}" with ID {workout["workoutId"]}.')
                valid_ids.append(str(workout['workoutId']))

    elif len(valid_ids) == 0:
        logging.warning('couldn\'t find any valid workout ID.')
        return

    for workout_id in valid_ids:
        res = client.delete_workout(workout_id)

    return None

config = {}

def import_workouts(plan_file, name_filter=None):

    # Load the file to get workout descriptions (added as comments in the YAML file)
    descriptions = {}
    with open(plan_file, 'r') as yfile:
        line_pattern = re.compile(r'^([^:]+):\s*#\s*(.*)\s*$')
        for line in yfile:
            m = line_pattern.match(line)
            if m:
                key = m.group(1)
                comment = m.group(2)
                descriptions[key] = comment

    with open(plan_file, 'r') as file:
        workouts = []
        import_json = yaml.safe_load(file)

        # remove the config entry, if present
        global config
        config = import_json.pop('config', {})

        expand_config(config)

        for name, steps in import_json.items():
            if name_filter and not re.search(name_filter, name):
                continue

            w = Workout("running", config.get('name_prefix', '') + name, descriptions.get(name, None))
            for step in steps:
                for k, v in step.items():
                  if not k.startswith('repeat'):
                    end_condition = get_end_condition(v)
                    ws_target=get_target(v)
                    ws = WorkoutStep(
                        0,
                        k,
                        get_description(v, ws_target),
                        end_condition=end_condition,
                        end_condition_value=get_end_condition_value(v, end_condition),
                        target=ws_target
                    )
                    w.add_step(ws)
                  else:
                      m = re.compile(r'^repeat\s+(\d+)$').match(k)
                      iterations = int(m.group(1))
                      # create the repetition step
                      ws = WorkoutStep(
                          0,
                          'repeat',
                          get_description(v),
                          end_condition='iterations',
                          end_condition_value=iterations
                      )
                      # create the repeated steps
                      for step in v:
                        for rk, rv in step.items():
                          end_condition = get_end_condition(rv)
                          rws_target=get_target(rv)
                          rws = WorkoutStep(
                              0,
                              rk,
                              get_description(rv, rws_target),
                              end_condition=end_condition,
                              end_condition_value=get_end_condition_value(rv, end_condition),
                              target=rws_target
                          )
                        ws.add_step(rws)
                        w.add_step(ws)

            #print(json.dumps(w.garminconnect_json(), indent=2))
            workouts.append(w)
        return workouts

def get_description(step_txt, target=None):
    description = None
    if ' -- ' in step_txt:
        description = step_txt[step_txt.find(' -- ') + 4:].strip()
    if target and target.target == 'pace.zone':
        avg_pace = (target.from_value + target.to_value) / 2
        avg_pace_kmph = avg_pace / 0.27778
        avg_pace_kmph_str = f'{avg_pace_kmph:.1f} kmph'
        if description:
            description += '\n' + avg_pace_kmph_str
        else:
            description = avg_pace_kmph_str
    return description

def get_end_condition(step_txt):
    step_txt = clean_step(step_txt)
    p_distance = re.compile(r'^\d+(m|km)\s?')
    p_time = re.compile(r'^\d+(min|h|s)\s?')
    p_iterations = re.compile(r'^\d+$')
    if p_time.match(step_txt):
        return 'time'
    elif p_distance.match(step_txt):
        return 'distance'
    elif p_iterations.match(step_txt):
        return 'iterations'
    return 'lap.button'

def get_end_condition_value(step_txt, condition_type=None):
    step_txt = clean_step(step_txt)

    if not condition_type:
        condition_type = get_end_condition(step_txt)
    
    if condition_type == 'time':
        p = re.compile(r'^(\d+)((min|h|s))\s?')
        m = p.match(step_txt)
        cv = int(m.group(1))
        tu = m.group(2)
        if tu == 'h':
            cv = cv * 60 * 60
        elif tu == 'min':
            cv = cv * 60
        elif tu == 's':
            cv = cv

        return str(cv)
    elif condition_type == 'distance':
        p = re.compile(r'^(\d+)((m|km))\s?')
        m = p.match(step_txt)
        cv = int(m.group(1))
        tu = m.group(2)
        if tu == 'km':
            cv = cv * 1000
        return str(cv)
    return None

def get_target(step_txt, verbose=False):
    step_txt = clean_step(step_txt)
    target_type = None
    target = None
    scale_min = 1
    scale_max = 1

    if ' in ' in step_txt:
        target_type = 'pace.zone'
        target = ms_to_pace(dist_time_to_ms(step_txt))
    elif ' @ ' in step_txt:
        target_type = 'pace.zone'
        parts = [p.strip() for p in step_txt.split(' @ ')]
        target = parts[1]

        if re.compile(r'^\d{1,2}:\d{1,2}(?:-\d{1,2}:\d{1,2})?').match(target):
            target = target
        else:
            while not re.compile(r'^\d{1,2}:\d{1,2}(?:-\d{1,2}:\d{1,2})?').match(target):
                # Check if the target is of type 75% marathon_pace
                tm = re.compile(r'^(\d+-?\d+)%\s*(\S+)$').match(target)
                if tm:
                    # Get the scale in the form 75% or 70-80%
                    scales = sorted([float(s)/100 for s in tm.group(1).split('-')])
                    scale_min = scale_max = scales[0]
                    if len(scales) == 2:
                        scale_max = scales[1]
                    target = tm.group(2).strip()

                # Check if the target is found in the paces config block
                if target in config['paces']:
                    target = config['paces'][target]
                else:
                    raise ValueError(f'Cannot find pace target \'{target}\' in workout step \'{step_txt}\'')
    elif ' @hr ' in step_txt:
        target_type = 'heart.rate.zone'
        parts = [p.strip() for p in step_txt.split(' @hr ')]
        target = parts[1]
        if target in config['heart_rates']:
            target = config['heart_rates'][target]

        if isinstance(target, int):
            target = f'{target}-{target}'            
    else: # No target
        return None

    if target_type == 'pace.zone':
        target_range = get_pace_range(target, config.get('margins', None))
        return Target(target_type, scale_min*pace_to_ms(target_range[0]), scale_max*pace_to_ms(target_range[1]))
    elif target_type == 'heart.rate.zone':
        if re.compile(r'^\d{2,3}-\d{2,3}$').match(target):
            target_range = [int(t) for t in target.split('-')]
            return Target(target_type, target_range[0], target_range[1])
        m = re.compile(r'^(z|zone)[-_]?([1-5])$').match(target)
        if m:
            return Target(target_type, zone=int(m.group(2)))
        raise ValueError('Invalid heart rate target: ' + step_txt)
        
    raise ValueError('Invalid step description: ' + step_txt)

def get_hr_range(step_txt):
    return None

def clean_step(step_txt):
    # remove description, if any
    if ' -- ' in step_txt:
        step_txt = step_txt[:step_txt.find(' -- ')].strip()
    return step_txt    

def expand_config(config):
    paces = config.get('paces', [])
    # If we find paces in <distance> in <time> format, convert them to mm:ss
    for pk, pv in paces.items():
        if re.compile('^.+ in .+$').match(pv.strip()):
            paces[pk] = ms_to_pace(dist_time_to_ms(pv))
    heart_rates = config.get('heart_rates', {})
    for hrk, hrv in heart_rates.items():
        hr_range = []
        hr_up = heart_rates.get('hr_up', 0)
        hr_down = heart_rates.get('hr_down', 0)

        # If we get an integer, this is a fixed hr. We leave it as it is.
        if isinstance(hrv, int):
            continue

        m = re.compile(r'^\s*(\d{2}-?\d{0,2})% (.+)\s*$').match(hrv)
        if m:
            ref_hr = m.group(2)
            if not ref_hr in heart_rates:
                raise ValueError(f'Cannot find heart rate target \'{ref_hr}\' in heart rate config. Found in \'{hrk}\')')
            ref_hr = heart_rates[ref_hr]
            hr_range = m.group(1)
            hr_range = hr_range.split('-')

            # If only one value was given, we apply the margins
            if len(hr_range) == 1:
                hr_range.append(hr_range[0])
                hr_range[0] -=  hr_down
                hr_range[1] += hr_up

            # Calculate the actual HR range based on the % value
            hr_range[0] = round(ref_hr * float(hr_range[0])/100)
            hr_range[1] = round(ref_hr * float(hr_range[1])/100)
            heart_rates[hrk] = '-'.join([str(hr) for hr in hr_range])
    
    return