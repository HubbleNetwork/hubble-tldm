/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * Thingy:53 application core. MCUboot boots this image, which only starts the
 * network core (see prj.conf), where the satellite application from
 * firmware/sat-zephyr runs and holds the device key.
 */

int main(void)
{
	return 0;
}
