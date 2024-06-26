# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013-2018 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import mimetypes
from datetime import datetime
from superdesk.tests import TestCase
from superdesk import get_resource_service
from superdesk.media.media_operations import process_file_from_stream
import os

from superdesk.metadata.item import GUID_TAG, ITEM_TYPE, CONTENT_TYPE
from superdesk.media.renditions import generate_renditions, get_renditions_spec
from superdesk.metadata import utils
from superdesk.upload import url_for_media
from superdesk import filemeta
from flask import current_app as app
from PIL import Image
import json


class BaseMediaEditorTestCase(TestCase):
    def setUp(self):
        super().setUp()
        dirname = os.path.dirname(os.path.realpath(__file__))
        image_path = os.path.normpath(os.path.join(dirname, "fixtures", self.filename))
        content_type = mimetypes.guess_type(image_path)[0]
        guid = utils.generate_guid(type=GUID_TAG)
        self.item = {
            "guid": guid,
            "version": 1,
            "_id": guid,
            ITEM_TYPE: CONTENT_TYPE.PICTURE,
            "mimetype": content_type,
            "versioncreated": datetime.now(),
        }

        with open(image_path, "rb") as f:
            _, content_type, file_metadata = process_file_from_stream(f, content_type=content_type)
            f.seek(0)
            file_id = app.media.put(f, filename=self.filename, content_type=content_type, metadata=file_metadata)
            filemeta.set_filemeta(self.item, file_metadata)
            f.seek(0)
            rendition_spec = get_renditions_spec()
            renditions = generate_renditions(
                f, file_id, [file_id], "image", content_type, rendition_spec, url_for_media
            )
            self.item["renditions"] = renditions
            f.seek(0)
        archive = get_resource_service("archive")
        archive.post([self.item])

    def do_edit(self, edit, item=None):
        """Helper method to test edition on current test media

        :param dict edit: edition instructions
        :return dict item: item with modified media
        """
        media_editor = get_resource_service("media_editor")
        request_data = {"edit": edit}
        if item is None:
            item_id = self.item["_id"]
            request_data["item_id"] = item_id
        else:
            for k in item:
                if isinstance(item[k], datetime):
                    item[k] = item[k].isoformat()
            for r in item["renditions"].values():
                r["media"] = str(r["media"])
            request_data["item"] = item
        docs = [request_data]
        with self.app.test_request_context(
            "media_editor", method="POST", content_type="application/json", data=json.dumps(request_data)
        ):
            media_editor.create(docs)

        return docs[0]

    def image(self, item, rendition):
        media_id = item["renditions"][rendition]["media"]
        media = app.media.get(media_id)
        return Image.open(media)


class MediaEditorTestCase(BaseMediaEditorTestCase):
    filename = "IPTC-PhotometadataRef-Std2017.1.jpg"

    def test_edition(self):
        """Test basic edition instructions"""
        item = self.do_edit({"contrast": 1.2, "rotate": "90"})
        image = self.image(item, "original")
        self.assertEqual(500, image.width)
        self.assertEqual(1000, image.height)

    def test_saturation(self):
        """Test saturation change"""
        item = self.do_edit({"saturation": 0})
        image = self.image(item, "original")
        # not sure how to test saturation, so just checking
        # the size remained the same
        self.assertEqual(1000, image.width)
        self.assertEqual(500, image.height)

    def test_update(self):
        """Test that item is updated correctly"""
        original_media_id = self.item["renditions"]["original"]["media"]
        item = self.do_edit({"rotate": "270", "saturation": "0"}, item=self.item)
        image = self.image(item, "original")
        self.assertEqual(500, image.width)
        self.assertEqual(1000, image.height)
        expected_media_id = item["renditions"]["original"]["media"]
        self.assertNotEqual(original_media_id, expected_media_id)
        self.assertEqual(item["renditions"]["original"]["media"], expected_media_id)
