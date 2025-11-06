#include <hubble/ble.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>

#include <stdint.h>
#include <stdlib.h>

#include "bt_time_service.h"

#include "key.c"
#include "utc.c"

LOG_MODULE_REGISTER(main, CONFIG_APP_LOG_LEVEL);


#define BLINK_PERIOD_S 1
#define ADV_UPDATE_PERIOD_S 300

/* The devicetree node identifier for the "led0" alias. */
#define LED0_NODE DT_ALIAS(led0)

// Buffer used for Hubble data
// Encrypted data will go in here for the advertisement.
#define HUBBLE_USER_BUFFER_LEN 31
static uint8_t _hubble_user_buffer[HUBBLE_USER_BUFFER_LEN];

/*
 * A build error on this line means your board is unsupported.
 * See the sample documentation for information on how to fix this.
 */
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

static uint16_t app_adv_uuids[1] = {
	HUBBLE_BLE_UUID,
};

static struct bt_data app_ad[2] = {
	BT_DATA(BT_DATA_UUID16_ALL, &app_adv_uuids, sizeof(app_adv_uuids)),
	{},
};

K_SEM_DEFINE(timer_sem, 0, 1);

static void timer_cb(struct k_timer *timer)
{
	k_sem_give(&timer_sem);
}

K_TIMER_DEFINE(message_timer, timer_cb, NULL);

static void blink_timer_cb(struct k_timer *timer)
{
	gpio_pin_toggle_dt(&led);
}
K_TIMER_DEFINE(blink_timer, blink_timer_cb, NULL);

int main(void)
{
	int err;

	if (!gpio_is_ready_dt(&led)) {
		return 0;
	}

	err = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
	if (err < 0) {
		return err;
	}

	LOG_DBG("Hubble Network BLE Beacon started");

	/* Synchrounosly initialize the Bluetooth subsystem. */
	err = bt_enable(NULL);
	if (err != 0) {
		LOG_ERR("Bluetooth init failed (err %d)", err);
		return err;
	}

#ifdef CONFIG_HUBBLE_TIME_SYNC
	int64_t current_time;

	current_time = bt_time_sync(K_FOREVER);
	if (current_time < 0) {
		LOG_ERR("Time sync failed (err %d)", err);
		return current_time;
	}
	utc_time = (uint64_t)current_time;
#endif

	err = hubble_ble_init(utc_time);
	if (err != 0) {
		LOG_ERR("Failed to initialize Hubble BLE Network");
		goto end;
	}

	err = hubble_ble_key_set(master_key);
	if (err != 0) {
		LOG_ERR("Failed to set the Hubble key");
		goto end;
	}

	/* Blink an LED as a "proof of life" */
	k_timer_start(
		&blink_timer,
		K_SECONDS(BLINK_PERIOD_S),
		K_SECONDS(BLINK_PERIOD_S));

	/* Update the message we send every ADV_UPDATE_PERIOD_S */
	k_timer_start(
		&message_timer,
		K_SECONDS(ADV_UPDATE_PERIOD_S),
		K_SECONDS(ADV_UPDATE_PERIOD_S));

	while (1) {
		size_t out_len = HUBBLE_USER_BUFFER_LEN;
		err = hubble_ble_advertise_get(NULL, 0, _hubble_user_buffer, &out_len);
		if (err != 0) {
			LOG_ERR("Failed to get the advertisement data");
			goto end;
		}
		app_ad[1].data_len = out_len;
		app_ad[1].type = BT_DATA_SVC_DATA16;
		app_ad[1].data = _hubble_user_buffer;

		LOG_DBG("Number of bytes in advertisement: %d", out_len);

		err = bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_NRPA,
					      BT_GAP_ADV_FAST_INT_MIN_2,
					      BT_GAP_ADV_FAST_INT_MAX_2, NULL),
				      app_ad, ARRAY_SIZE(app_ad), NULL, 0);
		if (err != 0) {
			LOG_ERR("Bluetooth advertisement failed (err %d)", err);
			goto end;
		}

		k_sem_take(&timer_sem, K_FOREVER);

		err = bt_le_adv_stop();
		if (err != 0) {
			LOG_ERR("Bluetooth advertisement stop failed (err %d)",
				err);
			goto end;
		}
	}

end:
	(void)bt_disable();
	return err;
}

