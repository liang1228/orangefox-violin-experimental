$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_base.mk)
$(call inherit-product, vendor/twrp/config/common.mk)
$(call inherit-product, device/xiaomi/violin/device.mk)

PRODUCT_DEVICE := violin
PRODUCT_NAME := twrp_violin
PRODUCT_BRAND := Xiaomi
PRODUCT_MODEL := 25053RP5CC
PRODUCT_MANUFACTURER := Xiaomi
