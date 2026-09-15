/*
 * Copyright (c) 2026 Hubble Network, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <stdint.h>
#include <pthread.h>

/* FreeRTOS */
#include <FreeRTOS.h>
#include <task.h>

/* TI Drivers */
#include <ti/drivers/Board.h>

/* Hubble Network */
#include <hubble/hubble.h>
#include <hubble/port/sys.h>
#include <hubble/sat/packet.h>

#include "key.c"

/* Stack size in bytes */
#define THREADSTACKSIZE 2048

/* Sleep interval between each sat packet */
#define SLEEP_PERIOD_MS 10000

/*
 * Payload is the device uptime in seconds, big-endian. hubble_sat_packet_get()
 * only accepts payload lengths of 0, 4, 9 or 13 bytes and rejects anything else
 * with -EINVAL, so this is the smallest non-empty payload the protocol allows.
 */
#define PAYLOAD_LEN 4U

static void put_be32(uint32_t value, uint8_t out[PAYLOAD_LEN])
{
	out[0] = (uint8_t)(value >> 24);
	out[1] = (uint8_t)(value >> 16);
	out[2] = (uint8_t)(value >> 8);
	out[3] = (uint8_t)value;
}

void *mainThread(void *arg0)
{
	struct hubble_sat_packet packet;
	uint8_t payload[PAYLOAD_LEN];
	int ret;

	(void)arg0;

	/*
	 * This sample uses the device uptime counter source, so it is
	 * acceptable to give the initial time as 0: the EID counter starts at
	 * 0 and advances with uptime, and no UTC time has to be provisioned.
	 */
	ret = hubble_init(0, master_key);
	if (ret != 0) {
		/* TODO: Call Error Handler */
		return NULL;
	}

	for (;;) {
		put_be32((uint32_t)(hubble_uptime_get() / 1000U), payload);

		ret = hubble_sat_packet_get(&packet, payload, sizeof(payload));
		if (ret != 0) {
			/* TODO: Call Error Handler */
			return NULL;
		}

		/*
		 * Set reliability to NONE. This will trigger a single
		 * transmission instead of a sequence. This is only for testing
		 * purposes and not recommended for production.
		 */
		ret = hubble_sat_packet_send(&packet,
					     HUBBLE_SAT_RELIABILITY_NONE);
		if (ret != 0) {
			/* TODO: Call Error Handler */
			return NULL;
		}
		vTaskDelay(pdMS_TO_TICKS(SLEEP_PERIOD_MS));
	}

	return NULL;
}

int main(void)
{
	pthread_t thread;
	pthread_attr_t attrs;
	struct sched_param priParam;
	int retc;

	/* initialize the system locks */
	Board_init();

	/* Initialize the attributes structure with default values */
	pthread_attr_init(&attrs);

	/* Set priority, detach state, and stack size attributes */
	priParam.sched_priority = 1;
	retc = pthread_attr_setschedparam(&attrs, &priParam);
	retc |= pthread_attr_setdetachstate(&attrs, PTHREAD_CREATE_DETACHED);
	retc |= pthread_attr_setstacksize(&attrs, THREADSTACKSIZE);
	if (retc != 0) {
		/* failed to set attributes */
		while (1) {
		}
	}

	retc = pthread_create(&thread, &attrs, mainThread, NULL);
	if (retc != 0) {
		/* pthread_create() failed */
		while (1) {
		}
	}

	/* Start the FreeRTOS scheduler */
	vTaskStartScheduler();

	return (0);
}
