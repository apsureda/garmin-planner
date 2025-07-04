import logging
import re
import datetime

from planner.garmin_client import GarminClient

def cmd_schedule_workouts(args):
    training_sessions = {}
    client = GarminClient(args.oauth_folder)
    logging.info(f'getting list of workouts.')
    workouts_list = client.list_workouts()
    wid_to_name = {}
    for workout in workouts_list:
        workout_name = workout['workoutName']
        workout_id = workout["workoutId"]
        wid_to_name[workout_id] = workout_name
        if re.search(args.training_plan, workout['workoutName']):
            logging.info(f'found workout named "{workout_name}" with ID {workout_id}.')
            training_sessions[workout_id] = workout_name

    training_plan = {}
    scheduled_plan = {}
    week_ids = []
    for k, v in training_sessions.items():
        res = re.search(r'\s(W\d\d)S(\d\d)\s', v)
        week_id = res.group(1)
        session = int(res.group(2))
        plan_week = training_plan.get(week_id, {})
        plan_day = plan_week.get(session, [])
        plan_day.append(k)
        plan_week[session] = plan_day
        training_plan[week_id] = plan_week
        if not week_id in week_ids:
            week_ids.append(week_id)

    week_ids = sorted(week_ids, reverse=args.reverse_order)
    training_plan = dict(sorted(training_plan.items(), reverse=args.reverse_order))
    train_weeks = len(week_ids)
    race_day = datetime.datetime.strptime(args.race_day, '%Y-%m-%d')
    first_monday = race_day + datetime.timedelta(days=-race_day.weekday(), weeks=-(train_weeks-2))

    for week_nb in range(0, len(week_ids)):
        plan = training_plan[week_ids[week_nb]]
        week_monday = first_monday + datetime.timedelta(weeks=+(week_nb-1))
        monday = week_monday.strftime('%Y-%m-%d')
        tuesday = (week_monday + datetime.timedelta(days=+1)).strftime('%Y-%m-%d')
        wednesday = (week_monday + datetime.timedelta(days=+2)).strftime('%Y-%m-%d')
        thursday = (week_monday + datetime.timedelta(days=+3)).strftime('%Y-%m-%d')
        friday = (week_monday + datetime.timedelta(days=+4)).strftime('%Y-%m-%d')
        saturday = (week_monday + datetime.timedelta(days=+5)).strftime('%Y-%m-%d')
        sunday = (week_monday + datetime.timedelta(days=+6)).strftime('%Y-%m-%d')
        sorted_plan = dict(sorted(plan.items()))
        plan_sessions = list(sorted_plan.keys())[-1]
        week_monday = first_monday + datetime.timedelta(weeks=+(week_nb-1))
        if plan_sessions == 2:
            scheduled_plan[saturday] = plan.get(1, None)
        elif plan_sessions == 2:
            scheduled_plan[wednesday] = plan.get(1, None)
            scheduled_plan[sunday] = plan.get(1, None)
        elif plan_sessions == 3:
            scheduled_plan[tuesday] = plan.get(1, None)
            scheduled_plan[thursday] = plan.get(2, None)
            scheduled_plan[sunday] = plan.get(3, None)
        elif plan_sessions == 4:
            scheduled_plan[tuesday] = plan.get(1, None)
            scheduled_plan[thursday] = plan.get(2, None)
            scheduled_plan[friday] = plan.get(3, None)
            scheduled_plan[sunday] = plan.get(4, None)
        elif plan_sessions == 5:
            scheduled_plan[tuesday] = plan.get(1, None)
            scheduled_plan[wednesday] = plan.get(2, None)
            scheduled_plan[thursday] = plan.get(3, None)
            scheduled_plan[friday] = plan.get(4, None)
            scheduled_plan[sunday] = plan.get(5, None)
        elif plan_sessions == 6:
            scheduled_plan[tuesday] = plan.get(1, None)
            scheduled_plan[wednesday] = plan.get(2, None)
            scheduled_plan[thursday] = plan.get(3, None)
            scheduled_plan[friday] = plan.get(4, None)
            scheduled_plan[saturday] = plan.get(5, None)
            scheduled_plan[sunday] = plan.get(6, None)
        elif plan_sessions == 7:
            scheduled_plan[monday] = plan.get(1, None)
            scheduled_plan[tuesday] = plan.get(2, None)
            scheduled_plan[wednesday] = plan.get(3, None)
            scheduled_plan[thursday] = plan.get(4, None)
            scheduled_plan[friday] = plan.get(5, None)
            scheduled_plan[saturday] = plan.get(6, None)
            scheduled_plan[sunday] = plan.get(7, None)
    scheduled_plan = dict(sorted(scheduled_plan.items()))
    for k, v in scheduled_plan.items():
        for workout in v:
            logging.info(f'scheduling workout {wid_to_name[workout]} ({workout}) on {k}')
            if not args.dry_run:
                client.schedule_workout(workout, k)
    return None


def cmd_unschedule_workouts(args):
    start_date = datetime.datetime.today()
    if args.start_date:
        start_date = datetime.datetime.strptime(args.start_date, '%Y-%m-%d')

    client = GarminClient(args.oauth_folder)
    search_year = start_date.year
    search_month = start_date.month
    while True:
        response = client.get_calendar(search_year, search_month)
        found_workouts = 0
        calendar_items = response.get('calendarItems', [])
        for item in calendar_items:
            if item.get('itemType', '') == 'workout':
                workout_name = item.get('title', '')
                workout_id = item.get('workoutId', None)
                schedule_id = item.get('id', None)
                schedule_date = item.get('date', None)
                date_cmp = datetime.datetime.strptime(schedule_date, '%Y-%m-%d')
                if date_cmp < start_date:
                    logging.info(f'ignoring past workout[{schedule_date}, {schedule_id}]: {workout_name} ({workout_id})')
                elif re.search(args.training_plan, workout_name):
                    found_workouts += 1
                    logging.info(f'Unscheduling workout [{schedule_date}, {schedule_id}]: {workout_name} ({workout_id})')
                    client.unschedule_workout(schedule_id)
        # if no workouts were fount in the latest iteration
        if found_workouts == 0:
            break
        # continue looking for workouts the followin month
        search_month += 1
        if search_month > 12:
            search_year += 1
            search_month = 1
