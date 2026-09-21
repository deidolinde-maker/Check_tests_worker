# Jenkins tests watchdog

This job monitors the continuous Jenkins jobs used by the landing tests and URL checker.

## Jenkins setup

1. Create a Pipeline job from this repository.
2. Add a Jenkins username/password credential with ID `jenkins_watchdog_api`.
   The password must be a Jenkins API token for that user.
3. Give the user permission to read and build the monitored jobs.
4. Check the job names in `targets.json`:
   - `code_checker_dev`
   - `Big_landing_test`
5. Save the job. The timer runs every ten minutes in `Europe/Moscow`.

The watchdog does not restart a running job. It triggers a new build only when there is no active build and the last completed build is older than the configured limit. A long-running build is reported in the watchdog console and is not forcibly aborted.

For the four big-test jobs, the configured parameters enable the continuous loop and preserve each job's `PROVIDER_SCOPE` when the watchdog has to recover it.
