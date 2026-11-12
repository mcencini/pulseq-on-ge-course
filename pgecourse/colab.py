"""Install GNU Octave on a Colab (or other Debian/Ubuntu) runtime.

Usage, in the first notebook cell:
    !pip -q install git+https://github.com/GEHC-External/pulseq-ge-course && python -m pgecourse.colab
"""

import shutil
import subprocess


def main() -> None:
    """Install Octave with apt if it is not already on the path."""
    if shutil.which("octave-cli") or shutil.which("octave"):
        print("Octave already installed")
        return
    subprocess.run(
        "apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y octave > /dev/null",
        shell=True,
        check=True,
    )
    print("Octave installed")


if __name__ == "__main__":
    main()
