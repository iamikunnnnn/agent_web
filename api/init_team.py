from agno.team import Team

from team.office_team import create_office_team

office_team = create_office_team(team_id="office_team")

all_teams = [
    office_team,
]

for team in list(all_teams):
    if not isinstance(team, Team):
        all_teams.remove(team)
