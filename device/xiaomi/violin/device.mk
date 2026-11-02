# Android 12.1 build-system compatibility setting, not the device's actual API.
# The connected OS3.0.305 device reports first API 35 and current API 36.
PRODUCT_SHIPPING_API_LEVEL := 32
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# Required by the Android 12 build when enabling TWRP's A/B slot support.
# This is not a validated OTA partition list; do not build or apply OTAs.
AB_OTA_PARTITIONS += boot recovery

PRODUCT_COPY_FILES += \
    device/xiaomi/violin/init.recovery.O1_asic.rc:$(TARGET_COPY_OUT_RECOVERY)/root/init.recovery.O1_asic.rc
