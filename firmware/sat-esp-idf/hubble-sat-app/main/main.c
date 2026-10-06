/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "nimble/nimble_port.h"

#include <hubble/hubble.h>
#include <hubble/port/sys.h>
#include <hubble/sat/packet.h>

#include "key.c"

#define SAT_TX_SLEEP_MS 10000

/*
 * Payload is the device uptime in seconds, big-endian. hubble_sat_packet_get()
 * only accepts payload lengths of 0, 4, 9 or 13 bytes and rejects anything else
 * with -EINVAL, so this is the smallest non-empty payload the protocol allows.
 */
#define PAYLOAD_LEN 4U

static const char *APP_TAG = "sat_continuous";

void app_main(void)
{
	esp_err_t err = 0;
	struct hubble_sat_packet pkt;
	uint8_t payload[PAYLOAD_LEN];
	uint32_t uptime_s;

	/* Initialize NVS — it is used to store PHY calibration data */
	err = nvs_flash_init();
	if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
	    err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_ERROR_CHECK(nvs_flash_erase());
		err = nvs_flash_init();
	}
	ESP_ERROR_CHECK(err);

	/* Init Bluetooth (NimBLE) */
	err = nimble_port_init();
	if (err != ESP_OK) {
		ESP_LOGE(APP_TAG, "Failed to init NimBLE stack, error: %d", err);
		return;
	}

	err = hubble_init(0, master_key);
	if (err != 0) {
		ESP_LOGE(APP_TAG,
			 "Failed to initialize Hubble Sat Network, error: %d",
			 err);
		return;
	}

	ESP_LOGI(APP_TAG, "Starting Sat Transmission");

	for (;;) {
		uptime_s = (uint32_t)(hubble_uptime_get() / 1000U);
		payload[0] = (uint8_t)(uptime_s >> 24);
		payload[1] = (uint8_t)(uptime_s >> 16);
		payload[2] = (uint8_t)(uptime_s >> 8);
		payload[3] = (uint8_t)uptime_s;

		err = hubble_sat_packet_get(&pkt, payload, sizeof(payload));
		if (err != 0) {
			ESP_LOGE(APP_TAG, "Failed to get Hubble Sat Network packet, error: %d",
				 err);
			return;
		}

		/*
		 * Set reliability to NONE. This will trigger a single
		 * transmission instead of a sequence. This is only for testing
		 * purposes and not recommended for production.
		 */
		err = hubble_sat_packet_send(&pkt, HUBBLE_SAT_RELIABILITY_NONE);
		if (err != 0) {
			ESP_LOGE(APP_TAG,
				 "Failed to transmit packet, error: %d", err);
			return;
		}

		vTaskDelay(pdMS_TO_TICKS(SAT_TX_SLEEP_MS));
	}
}
