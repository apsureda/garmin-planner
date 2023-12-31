SPORT_TYPES = {
    "running": 1,
}

STEP_TYPES = {"warmup": 1, "cooldown": 2, "interval": 3, "recovery": 4, "rest": 5, "repeat":6, "other": 7}

END_CONDITIONS = {
    "lap.button": 1,
    "time": 2,
    "distance": 3,
    "iterations": 7,
}

TARGET_TYPES = {
    "no.target": 1,
    "power.zone": 2,
    "cadence.zone": 3,
    "heart.rate.zone": 4,
    "speed.zone": 5,
    "pace.zone": 6,  # meters per second
}

class Workout:
    def __init__(self, sport_type, name):
        self.sport_type = sport_type
        self.workout_name = name
        self.workout_steps = []

    def add_step(self, step):
        if step.order == 0:
            step.order = len(self.workout_steps) + 1
        self.workout_steps.append(step)

    def garminconnect_json(self):
        return {
            "sportType": {
                "sportTypeId": SPORT_TYPES[self.sport_type],
                "sportTypeKey": self.sport_type,
            },
            "workoutName": self.workout_name,
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": {
                        "sportTypeId": SPORT_TYPES[self.sport_type],
                        "sportTypeKey": self.sport_type,
                    },
                    "workoutSteps": [step.garminconnect_json() for step in self.workout_steps],
                }
            ],
        }

class WorkoutStep:
    def __init__(
        self,
        order,
        step_type,
        description = '',
        end_condition="lap.button",
        end_condition_value=None,
        target=None,
    ):
        """Valid end condition values:
        - distance: '2.0km', '1.125km', '1.6km'
        - time: 0:40, 4:20
        - lap.button
        """
        self.order = order
        self.step_type = step_type
        self.description = description
        self.end_condition = end_condition
        self.end_condition_value = end_condition_value
        self.target = target or Target()
        self.child_step_id = 1 if self.step_type == 'repeat' else None
        self.workout_steps = []

    def add_step(self, step):
        step.child_step_id = self.child_step_id
        if step.order == 0:
            step.order = len(self.workout_steps) + 1
        self.workout_steps.append(step)

    def end_condition_unit(self):
        if self.end_condition and self.end_condition.endswith("km"):
            return {"unitKey": "kilometer"}
        else:
            return None

    def parsed_end_condition_value(self):
        # distance
        if self.end_condition == 'distance' and self.end_condition_value and self.end_condition_value.endswith("km"):
            return int(float(self.end_condition_value.replace("km", "")) * 1000)

        # time
        elif self.end_condition == 'time' and self.end_condition_value and ":" in self.end_condition_value:
            m, s = [int(x) for x in self.end_condition_value.split(":")]
            return m * 60 + s
        else:
            return self.end_condition_value

    def garminconnect_json(self):
        base_json = {
            "type": 'RepeatGroupDTO' if self.step_type == 'repeat' else 'ExecutableStepDTO',
            "stepId": None,
            "stepOrder": self.order,
            "childStepId": self.child_step_id,
            "stepType": {
                "stepTypeId": STEP_TYPES[self.step_type],
                "stepTypeKey": self.step_type,
            },
            "endCondition": {
                "conditionTypeKey": self.end_condition,
                "conditionTypeId": END_CONDITIONS[self.end_condition],
            },
            "endConditionValue": self.parsed_end_condition_value(),
        }

        if len(self.workout_steps) > 0:
            base_json["workoutSteps"] = [step.garminconnect_json() for step in self.workout_steps]

        if self.step_type == 'repeat':
            base_json['smartRepeat'] = True
            base_json['numberOfIterations'] = self.end_condition_value
        else:
            base_json.update({
                "description": self.description,
                "preferredEndConditionUnit": self.end_condition_unit(),
                "endConditionCompare": None,
                "endConditionZone": None,
                **self.target.garminconnect_json(),
            })
        return base_json

class Target:
    def __init__(self, target="no.target", to_value=None, from_value=None, zone=None):
        self.target = target
        self.to_value = to_value
        self.from_value = from_value
        self.zone = zone

    def garminconnect_json(self):
        return {
            "targetType": {
                "workoutTargetTypeId": TARGET_TYPES[self.target],
                "workoutTargetTypeKey": self.target,
            },
            "targetValueOne": self.to_value,
            "targetValueTwo": self.from_value,
            "zoneNumber": self.zone,
        }
