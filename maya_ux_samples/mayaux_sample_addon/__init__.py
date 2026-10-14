"""MayaUX Shelf 호환성 검증용 '외부' 애드온 샘플.

MayaUX 와 무관한 서드파티 애드온처럼 동작한다. Shelf 의 Custom 탭이 이 애드온의
Operator 3개를 bl_idname 으로 호출한다. 비활성화하면 해당 버튼이 비활성으로 바뀐다.
"""

import random

import bpy


class MAYAUX_SAMPLE_OT_center_pivot(bpy.types.Operator):
    """선택 오브젝트의 원점을 바운딩 박스 중심으로 (Maya Center Pivot)"""

    bl_idname = "mayaux_sample.center_pivot"
    bl_label = "Center Pivot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(context.selected_editable_objects)

    def execute(self, context):
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        return {"FINISHED"}


class MAYAUX_SAMPLE_OT_freeze_transforms(bpy.types.Operator):
    """위치·회전·스케일을 메시에 적용 (Maya Freeze Transformations)"""

    bl_idname = "mayaux_sample.freeze_transforms"
    bl_label = "Freeze Transformations"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(context.selected_editable_objects)

    def execute(self, context):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        return {"FINISHED"}


class MAYAUX_SAMPLE_OT_random_color(bpy.types.Operator):
    """선택 오브젝트의 뷰포트 표시 색을 무작위로"""

    bl_idname = "mayaux_sample.random_color"
    bl_label = "Random Viewport Color"
    bl_options = {"REGISTER", "UNDO"}

    seed: bpy.props.IntProperty(name="Seed", default=0)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        rng = random.Random(self.seed or None)
        for ob in context.selected_objects:
            ob.color = (rng.random(), rng.random(), rng.random(), 1.0)
        return {"FINISHED"}


_classes = (MAYAUX_SAMPLE_OT_center_pivot, MAYAUX_SAMPLE_OT_freeze_transforms, MAYAUX_SAMPLE_OT_random_color)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
