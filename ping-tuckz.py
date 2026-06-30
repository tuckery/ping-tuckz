import ping_tuckz_core as core


def print_cli_log(message, status=None, latency=None, timestamp=None):
    if status in ('HIGH', 'TIMEOUT'):
        print(f"{core.RED}{message}{core.RESET}")
    elif status == 'MEDIUM':
        print(f"{core.ORANGE}{message}{core.RESET}")
    else:
        print(message)


def main():
    args = core.parse_args()
    try:
        core.run_monitor(args.target, on_log=print_cli_log, refresh_html=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
