"""Pruebas para config.py, incluyendo extract_frame_number."""

import unittest

from bcr.config import extract_frame_number


class TestExtractFrameNumber(unittest.TestCase):
    """Prueba extract_frame_number con distintos patrones de nombre."""

    def test_six_digits_before_extension(self) -> None:
        """6 digitos antes de .ext: caso standard."""
        self.assertEqual(extract_frame_number("Result_000001.exr"), 1)

    def test_six_digits_in_middle_of_name(self) -> None:
        """6 digitos en medio del nombre."""
        self.assertEqual(extract_frame_number("File_Output_001_000001.exr"), 1)

    def test_six_digits_node_name_with_numbers(self) -> None:
        """Nombre con numeros internos + 6 digitos de frame."""
        self.assertEqual(extract_frame_number("File_Output_000023_000001.exr"), 1)

    def test_zero_padded_six_digits(self) -> None:
        """Frame 123456 con padding completo."""
        self.assertEqual(extract_frame_number("Result_123456.exr"), 123456)

    def test_six_digits_only_part_png(self) -> None:
        """6 digitos en nombre .png."""
        self.assertEqual(extract_frame_number("frame_000001.png"), 1)

    def test_five_digits_returns_none(self) -> None:
        """5 digitos: no debe calce (quiere exactamente 6)."""
        self.assertIsNone(extract_frame_number("frame_00001.png"))

    def test_seven_digits_returns_none(self) -> None:
        """7 digitos: no debe calce."""
        self.assertIsNone(extract_frame_number("file_name0000001.exr"))

    def test_single_digit_returns_none(self) -> None:
        """1 digito: no debe calce."""
        self.assertIsNone(extract_frame_number("file_name1frane.exr"))

    def test_no_digits_returns_none(self) -> None:
        """Sin digitos: None."""
        self.assertIsNone(extract_frame_number("output.exr"))

    def test_empty_string_returns_none(self) -> None:
        """String vacio: None."""
        self.assertIsNone(extract_frame_number(""))

    def test_six_digits_surrounded_by_non_digits(self) -> None:
        """6 digitos entre letras y extension."""
        self.assertEqual(extract_frame_number("Render_000001_final.exr"), 1)

    def test_six_digits_not_adjacent_to_other_digits(self) -> None:
        """6 digitos no adyacentes a otros digitos."""
        self.assertEqual(extract_frame_number("a_000001_b.exr"), 1)

    def test_six_digits_at_start(self) -> None:
        """6 digitos al inicio del nombre."""
        self.assertEqual(extract_frame_number("000001_result.exr"), 1)

    def test_frame_extracted_from_full_path(self) -> None:
        """Ruta completa con directorios: extrae solo del nombre."""
        path = "/content/render_tmp/tmp/Result_000001.exr"
        self.assertEqual(extract_frame_number(path), 1)

    def test_multilayer_output_name(self) -> None:
        """Nombre que producira un nodo multilayer."""
        self.assertEqual(
            extract_frame_number("/content/render_tmp/salida/File_Output_001_000001.exr"),
            1,
        )

    def test_single_layer_output_name(self) -> None:
        """Nombre que producira un nodo single-layer."""
        self.assertEqual(
            extract_frame_number("/content/render_tmp/tmp/Result_000001.exr"),
            1,
        )
