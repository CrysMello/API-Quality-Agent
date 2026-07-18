def mask_secret(
    value: str,
    *,
    visible_prefix: int = 4,
    visible_suffix: int = 4,
    mask_char: str = "*",
) -> str:
    if not isinstance(value, str):
        raise TypeError("value deve ser uma string.")
    length = len(value)
    if length == 0:
        return value
    if length <= visible_prefix + visible_suffix:
        return mask_char * length
    prefix = value[:visible_prefix]
    suffix = value[-visible_suffix:] if visible_suffix else ""
    masked_length = length - visible_prefix - visible_suffix
    return f"{prefix}{mask_char * masked_length}{suffix}"
