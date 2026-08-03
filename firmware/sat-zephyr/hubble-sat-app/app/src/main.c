/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <hubble/hubble.h>
#include <hubble/sat.h>
#include <hubble/sat/packet.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/byteorder.h>

#include <stdint.h>

#include "key.c"

LOG_MODULE_REGISTER(main, CONFIG_APP_LOG_LEVEL);

/*
 * Payload is a 4 byte big-endian sequence number, incremented once per packet.
 * hubble_sat_packet_get() only accepts lengths of 0, 4, 9 or 13 bytes and
 * rejects anything else with -EINVAL, so this is the smallest non-empty
 * payload the protocol allows.
 *
 * Gaps in the received sequence are the point: paired with RELIABILITY_NONE
 * below, every packet is sent exactly once, so the numbers arriving at the
 * console are a direct measure of delivery rate. The counter restarts at 0 on
 * reboot.
 */
#define PAYLOAD_LEN 4U

int main(void)
{
	struct hubble_sat_packet pkt;
	uint8_t payload[PAYLOAD_LEN];
	uint32_t seq = 0;
	int err;

	LOG_DBG("Hubble Network Satellite application started");

	/*
	 * Uses the device uptime counter source
	 * (CONFIG_HUBBLE_COUNTER_SOURCE_DEVICE_UPTIME), so no UTC time is
	 * needed: the initial EID counter is 0 and advances with uptime.
	 */
	err = hubble_init(0, master_key);
	if (err != 0) {
		LOG_ERR("Failed to initialize Hubble Sat Network");
		return err;
	}

	while (1) {
		sys_put_be32(seq++, payload);

		err = hubble_sat_packet_get(&pkt, payload, sizeof(payload));
		if (err != 0) {
			LOG_ERR("Failed to get Hubble Sat Network packet");
			return err;
		}

		/*
		 * NONE transmits the packet exactly once. NORMAL and HIGH
		 * would repeat the same packet 8 or 16 times, so one logical
		 * packet would arrive as several identical copies and mask
		 * how many were lost -- which is what we are measuring here.
		 *
		 * Expect most packets not to arrive: a lone transmission has
		 * to coincide with a satellite pass, and NONE is excluded from
		 * the SDK's clock-drift retry compensation. The gaps are the
		 * signal, not a fault.
		 *
		 * NONE also makes this call return immediately rather than
		 * blocking for a retry sequence, so the loop period really is
		 * CONFIG_APP_SAT_TX_INTERVAL_SECONDS.
		 */
		err = hubble_sat_packet_send(&pkt, HUBBLE_SAT_RELIABILITY_NONE);
		if (err != 0) {
			LOG_ERR("Failed to transmit packet");
			return err;
		}

		k_sleep(K_SECONDS(CONFIG_APP_SAT_TX_INTERVAL_SECONDS));
	}

	return 0;
}
