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
 * Payload is the device uptime in seconds, big-endian. hubble_sat_packet_get()
 * only accepts lengths of 0, 4, 9 or 13 bytes and rejects anything else with
 * -EINVAL, so this is the smallest non-empty payload the protocol allows.
 */
#define PAYLOAD_LEN 4U

int main(void)
{
	struct hubble_sat_packet pkt;
	uint8_t payload[PAYLOAD_LEN];
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
		sys_put_be32((uint32_t)(k_uptime_get() / MSEC_PER_SEC), payload);

		err = hubble_sat_packet_get(&pkt, payload, sizeof(payload));
		if (err != 0) {
			LOG_ERR("Failed to get Hubble Sat Network packet");
			return err;
		}

		/*
		 * NORMAL retransmits the packet 8 times at 20 second
		 * intervals. A satellite pass is short and infrequent, so a
		 * single unrepeated transmission is unlikely to be received.
		 * This call blocks until the transmission period completes.
		 */
		err = hubble_sat_packet_send(&pkt, HUBBLE_SAT_RELIABILITY_NORMAL);
		if (err != 0) {
			LOG_ERR("Failed to transmit packet");
			return err;
		}

		k_sleep(K_SECONDS(CONFIG_APP_SAT_TX_INTERVAL_SECONDS));
	}

	return 0;
}
